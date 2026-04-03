"""
Inventory service.
All write paths (receipt/issue/transfer/adjustment) run inside an explicit
db.session transaction. Costing method is locked after first transaction per lot.
"""
import json
import re
from datetime import datetime, timezone

from app.extensions import db
from app.models.inventory import (
    Warehouse, Bin, InventoryLot, InventoryTransaction,
    CostLayer, AvgCostSnapshot, CycleCount, CycleCountLine, SkuCostingPolicy,
)
from app.models.user import User
from app.models.audit import AuditLog
from app.errors import NotFoundError, UnprocessableError, AppError
from flask import g


def _cid() -> str:
    return getattr(g, "correlation_id", "n/a")


# Barcode: alphanumeric, hyphens, 1-128 chars (covers UPC, EAN, Code128)
_BARCODE_RE = re.compile(r'^[A-Za-z0-9\-]{1,128}$')
# RFID: hex string, 1-128 chars (EPC tag format)
_RFID_RE = re.compile(r'^[A-Fa-f0-9]{1,128}$')


def _validate_barcode(value: str | None) -> None:
    """Validate barcode format if provided."""
    if value is None:
        return
    value = str(value)
    if not _BARCODE_RE.match(value):
        raise AppError(
            "invalid_barcode_format",
            "Barcode must be 1-128 alphanumeric characters or hyphens",
            field="barcode",
            status_code=400,
        )


def _validate_rfid(value: str | None) -> None:
    """Validate RFID format if provided."""
    if value is None:
        return
    value = str(value)
    if not _RFID_RE.match(value):
        raise AppError(
            "invalid_rfid_format",
            "RFID must be 1-128 hexadecimal characters",
            field="rfid",
            status_code=400,
        )


def _serialize_serial_numbers(val) -> str | None:
    """Normalize API serial_numbers (list or JSON string) to stored JSON array text."""
    if val is None:
        return None
    if isinstance(val, list):
        return json.dumps([str(x) for x in val])
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return json.dumps([s])
        if isinstance(parsed, list):
            return json.dumps([str(x) for x in parsed])
        return json.dumps([str(parsed)])
    raise AppError("invalid_serial_numbers", "serial_numbers must be a list or JSON string",
                   field="serial_numbers", status_code=400)


def _consume_fifo_layers(sku_id, warehouse_id, qty: int) -> None:
    """
    Consume FIFO cost layers oldest-first for the issued quantity.
    Silently handles orphaned qty (e.g. after zero-cost transfer receipts).
    """
    remaining = qty
    layers = (
        CostLayer.query
        .filter(
            CostLayer.sku_id == sku_id,
            CostLayer.warehouse_id == warehouse_id,
            CostLayer.quantity_remaining > 0,
        )
        .order_by(CostLayer.received_at.asc())
        .all()
    )
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.quantity_remaining, remaining)
        layer.quantity_remaining -= take
        remaining -= take


def _current_cost_usd(sku_id, warehouse_id, costing_method: str) -> float:
    """
    Return the current unit cost for a lot location.
    - moving_average: read AvgCostSnapshot
    - fifo: weighted average of remaining cost layers
    """
    if costing_method == "moving_average":
        snap = AvgCostSnapshot.query.filter_by(sku_id=sku_id, warehouse_id=warehouse_id).first()
        return round(snap.avg_cost_usd, 6) if snap else 0.0
    # FIFO: weighted average of remaining layers
    layers = CostLayer.query.filter(
        CostLayer.sku_id == sku_id,
        CostLayer.warehouse_id == warehouse_id,
        CostLayer.quantity_remaining > 0,
    ).all()
    total_qty = sum(layer.quantity_remaining for layer in layers)
    total_value = sum(layer.unit_cost_usd * layer.quantity_remaining for layer in layers)
    return round(total_value / total_qty, 6) if total_qty else 0.0


class InventoryService:

    # --- Warehouse & Bin ---

    @staticmethod
    def create_warehouse(data: dict) -> Warehouse:
        cid = data.get("community_id")
        if cid:
            from app.services.community_service import CommunityService
            CommunityService._get_or_404(cid)
        wh = Warehouse(
            name=data["name"],
            location=data["location"],
            notes=data.get("notes"),
            community_id=cid or None,
        )
        db.session.add(wh)
        db.session.commit()
        return wh

    @staticmethod
    def list_warehouses() -> list:
        return [w.to_dict() for w in Warehouse.query.all()]

    @staticmethod
    def create_bin(warehouse_id: str, data: dict) -> Bin:
        wh = db.session.get(Warehouse, warehouse_id)
        if wh is None:
            raise NotFoundError("warehouse")
        b = Bin(warehouse_id=warehouse_id, bin_code=data["bin_code"], description=data.get("description"))
        db.session.add(b)
        db.session.commit()
        return b

    @staticmethod
    def list_bins(warehouse_id: str) -> list:
        return [b.to_dict() for b in Bin.query.filter_by(warehouse_id=warehouse_id).all()]

    # --- Inventory movements ---

    @staticmethod
    def _get_or_create_lot(sku_id, warehouse_id, bin_id, lot_number, costing_method) -> InventoryLot:
        # SKU-level costing policy: first receipt for a SKU locks the method for all lots/warehouses
        if costing_method:
            policy = db.session.get(SkuCostingPolicy, sku_id)
            if policy is None:
                policy = SkuCostingPolicy(sku_id=sku_id, costing_method=costing_method)
                db.session.add(policy)
                db.session.flush()
            elif policy.costing_method != costing_method:
                raise UnprocessableError(
                    "costing_method_locked",
                    f"SKU costing method is locked to '{policy.costing_method}' "
                    f"from the first transaction",
                )

        lot = InventoryLot.query.filter_by(
            sku_id=sku_id, warehouse_id=warehouse_id, bin_id=bin_id, lot_number=lot_number
        ).first()
        if lot is None:
            from app.models.catalog import Product

            prod = db.session.get(Product, sku_id)
            threshold = int(prod.safety_stock_threshold or 0) if prod else 0
            lot = InventoryLot(
                sku_id=sku_id, warehouse_id=warehouse_id, bin_id=bin_id,
                lot_number=lot_number, costing_method=costing_method,
                safety_stock_threshold=threshold,
            )
            db.session.add(lot)
            db.session.flush()
        elif costing_method and lot.costing_method != costing_method:
            # Per-lot immutability (also enforced by DB trigger)
            raise UnprocessableError("costing_method_locked",
                                     "Costing method cannot be changed after first transaction")
        return lot

    @staticmethod
    def record_receipt(data: dict, actor: User) -> InventoryTransaction:
        _validate_barcode(data.get("barcode"))
        _validate_rfid(data.get("rfid"))
        lot = InventoryService._get_or_create_lot(
            data["sku_id"], data["warehouse_id"], data.get("bin_id"),
            data.get("lot_number"), data.get("costing_method", "fifo"),
        )
        qty = int(data["quantity"])
        lot.on_hand_qty += qty
        if data.get("barcode"):
            lot.barcode = str(data["barcode"])[:128]
        if data.get("rfid"):
            lot.rfid = str(data["rfid"])[:128]
        serials = _serialize_serial_numbers(data.get("serial_numbers"))
        if serials is not None:
            lot.serial_numbers = serials
        occurred_at = (datetime.fromisoformat(data["occurred_at"])
                       if data.get("occurred_at") else datetime.now(timezone.utc))

        txn = InventoryTransaction(
            type="receipt", sku_id=lot.sku_id, warehouse_id=lot.warehouse_id,
            bin_id=lot.bin_id, lot_id=lot.lot_id, quantity_delta=qty,
            actor_id=actor.user_id, occurred_at=occurred_at,
            correlation_id=_cid(), reference=data.get("notes"),
            barcode=(str(data["barcode"])[:128] if data.get("barcode") else None),
            rfid=(str(data["rfid"])[:128] if data.get("rfid") else None),
            serial_numbers=serials,
        )
        db.session.add(txn)

        unit_cost = float(data.get("unit_cost_usd", 0))
        if lot.costing_method == "fifo":
            db.session.add(CostLayer(
                sku_id=lot.sku_id, warehouse_id=lot.warehouse_id,
                quantity_remaining=qty, unit_cost_usd=unit_cost, received_at=occurred_at,
            ))
        else:  # moving_average
            _update_avg_cost(lot.sku_id, lot.warehouse_id, qty, unit_cost)

        db.session.commit()
        return txn

    @staticmethod
    def record_issue(data: dict, actor: User) -> InventoryTransaction:
        _validate_barcode(data.get("barcode"))
        _validate_rfid(data.get("rfid"))
        lot = InventoryLot.query.filter_by(
            sku_id=data["sku_id"], warehouse_id=data["warehouse_id"],
            bin_id=data.get("bin_id"), lot_number=data.get("lot_number"),
        ).first()
        if lot is None:
            raise NotFoundError("inventory_lot")
        qty = int(data["quantity"])
        if lot.on_hand_qty < qty:
            raise UnprocessableError("insufficient_stock", "Insufficient on-hand quantity")

        lot.on_hand_qty -= qty
        # Issue resets slow-moving timer and clears the slow-moving flag
        lot.last_issue_at = datetime.now(timezone.utc)
        lot.slow_moving = False

        occurred_at = (datetime.fromisoformat(data["occurred_at"])
                       if data.get("occurred_at") else datetime.now(timezone.utc))

        serials = _serialize_serial_numbers(data.get("serial_numbers"))
        txn = InventoryTransaction(
            type="issue", sku_id=lot.sku_id, warehouse_id=lot.warehouse_id,
            bin_id=lot.bin_id, lot_id=lot.lot_id, quantity_delta=-qty,
            reference=data.get("reference"), actor_id=actor.user_id,
            occurred_at=occurred_at, correlation_id=_cid(),
            barcode=(str(data["barcode"])[:128] if data.get("barcode") else lot.barcode),
            rfid=(str(data["rfid"])[:128] if data.get("rfid") else lot.rfid),
            serial_numbers=serials if serials is not None else lot.serial_numbers,
        )
        db.session.add(txn)

        # Consume FIFO cost layers oldest-first; decrement avg-cost snapshot for MA lots
        if lot.costing_method == "fifo":
            _consume_fifo_layers(lot.sku_id, lot.warehouse_id, qty)
        else:
            _decrement_avg_cost(lot.sku_id, lot.warehouse_id, qty)

        db.session.commit()
        return txn

    @staticmethod
    def record_transfer(data: dict, actor: User) -> list:
        _validate_barcode(data.get("barcode"))
        _validate_rfid(data.get("rfid"))
        # 1. Look up source lot (raises if not found)
        source_lot = InventoryLot.query.filter_by(
            sku_id=data["sku_id"],
            warehouse_id=data["from_warehouse_id"],
            bin_id=data.get("from_bin_id"),
        ).first()
        if source_lot is None:
            raise NotFoundError("inventory_lot")

        # 2. Capture cost and costing method before any mutation
        inherited_method = source_lot.costing_method
        transfer_cost = _current_cost_usd(data["sku_id"], data["from_warehouse_id"], inherited_method)

        qty = int(data["quantity"])
        occurred_at = (datetime.fromisoformat(data["occurred_at"])
                       if data.get("occurred_at") else datetime.now(timezone.utc))

        # 3. Issue-side mutations (no commit)
        if source_lot.on_hand_qty < qty:
            raise UnprocessableError("insufficient_stock", "Insufficient on-hand quantity")
        source_lot.on_hand_qty -= qty
        source_lot.last_issue_at = datetime.now(timezone.utc)
        source_lot.slow_moving = False

        issue_txn = InventoryTransaction(
            type="issue", sku_id=source_lot.sku_id, warehouse_id=source_lot.warehouse_id,
            bin_id=source_lot.bin_id, lot_id=source_lot.lot_id, quantity_delta=-qty,
            reference=data.get("reference"), actor_id=actor.user_id,
            occurred_at=occurred_at, correlation_id=_cid(),
        )
        db.session.add(issue_txn)

        if inherited_method == "fifo":
            _consume_fifo_layers(source_lot.sku_id, source_lot.warehouse_id, qty)
        else:
            _decrement_avg_cost(source_lot.sku_id, source_lot.warehouse_id, qty)

        # 4. Receipt-side mutations (no commit)
        dest_lot = InventoryService._get_or_create_lot(
            data["sku_id"], data["to_warehouse_id"], data.get("to_bin_id"),
            data.get("lot_number"), inherited_method,
        )
        dest_lot.on_hand_qty += qty

        receipt_txn = InventoryTransaction(
            type="receipt", sku_id=dest_lot.sku_id, warehouse_id=dest_lot.warehouse_id,
            bin_id=dest_lot.bin_id, lot_id=dest_lot.lot_id, quantity_delta=qty,
            actor_id=actor.user_id, occurred_at=occurred_at,
            correlation_id=_cid(), reference=data.get("notes"),
        )
        db.session.add(receipt_txn)

        if inherited_method == "fifo":
            db.session.add(CostLayer(
                sku_id=dest_lot.sku_id, warehouse_id=dest_lot.warehouse_id,
                quantity_remaining=qty, unit_cost_usd=transfer_cost, received_at=occurred_at,
            ))
        else:
            _update_avg_cost(dest_lot.sku_id, dest_lot.warehouse_id, qty, transfer_cost)

        # 5. Single atomic commit
        db.session.commit()
        return [issue_txn, receipt_txn]

    @staticmethod
    def record_adjustment(data: dict, actor: User) -> dict:
        if not data.get("reason"):
            raise AppError("reason_required", "reason is required for adjustments",
                           field="reason", status_code=400)
        lot = InventoryLot.query.filter_by(
            sku_id=data["sku_id"], warehouse_id=data["warehouse_id"], bin_id=data.get("bin_id")
        ).first()
        if lot is None:
            raise NotFoundError("inventory_lot")
        delta = int(data["quantity_delta"])
        before_qty = lot.on_hand_qty
        lot.on_hand_qty += delta
        occurred_at = (datetime.fromisoformat(data["occurred_at"])
                       if data.get("occurred_at") else datetime.now(timezone.utc))

        txn = InventoryTransaction(
            type="adjustment", sku_id=lot.sku_id, warehouse_id=lot.warehouse_id,
            bin_id=lot.bin_id, lot_id=lot.lot_id, quantity_delta=delta,
            reason=data["reason"], actor_id=actor.user_id,
            occurred_at=occurred_at, correlation_id=_cid(),
        )
        db.session.add(txn)

        audit = AuditLog(
            action_type="inventory", actor_id=actor.user_id,
            target_type="inventory_lot", target_id=str(lot.lot_id),
            before_state=f'{{"qty": {before_qty}}}',
            after_state=f'{{"qty": {lot.on_hand_qty}}}',
            correlation_id=_cid(),
        )
        db.session.add(audit)
        db.session.commit()
        return {"transaction": txn.to_dict(), "audit_log_id": str(audit.log_id)}

    @staticmethod
    def record_cycle_count(data: dict, actor: User) -> dict:
        cc = CycleCount(
            warehouse_id=data["warehouse_id"],
            actor_id=actor.user_id,
            counted_at=datetime.fromisoformat(data["counted_at"]),
        )
        db.session.add(cc)
        db.session.flush()

        lines = []
        for line_data in data.get("lines", []):
            lot = InventoryLot.query.filter_by(
                sku_id=line_data["sku_id"], warehouse_id=data["warehouse_id"],
                bin_id=line_data.get("bin_id"),
            ).first()
            system_qty = lot.on_hand_qty if lot else 0
            counted_qty = int(line_data["counted_qty"])
            variance = counted_qty - system_qty
            if variance != 0 and not line_data.get("variance_reason"):
                raise AppError("variance_reason_required",
                               "variance_reason is required when variance != 0", status_code=400)
            ccl = CycleCountLine(
                cycle_count_id=cc.cycle_count_id,
                sku_id=line_data["sku_id"],
                bin_id=line_data.get("bin_id"),
                system_qty=system_qty,
                counted_qty=counted_qty,
                variance=variance,
                variance_reason=line_data.get("variance_reason"),
            )
            db.session.add(ccl)
            lines.append(ccl)

        db.session.commit()
        return {"cycle_count_id": str(cc.cycle_count_id), "lines": [line.to_dict() for line in lines]}

    @staticmethod
    def query_stock(params: dict) -> dict:
        q = InventoryLot.query
        if params.get("sku_id"):
            q = q.filter(InventoryLot.sku_id == params["sku_id"])
        if params.get("warehouse_id"):
            q = q.filter(InventoryLot.warehouse_id == params["warehouse_id"])
        if params.get("bin_id"):
            q = q.filter(InventoryLot.bin_id == params["bin_id"])
        if params.get("below_safety_stock"):
            q = q.filter(InventoryLot.on_hand_qty < InventoryLot.safety_stock_threshold)
        if params.get("slow_moving"):
            q = q.filter(InventoryLot.slow_moving.is_(True))

        lots = q.all()
        items = []
        for lot in lots:
            d = lot.to_dict()
            d["below_safety_stock"] = lot.on_hand_qty < lot.safety_stock_threshold
            d["current_cost_usd"] = _current_cost_usd(lot.sku_id, lot.warehouse_id, lot.costing_method)
            items.append(d)
        return {"items": items}

    @staticmethod
    def list_transactions(params: dict) -> dict:
        q = InventoryTransaction.query
        if params.get("sku_id"):
            q = q.filter(InventoryTransaction.sku_id == params["sku_id"])
        if params.get("warehouse_id"):
            q = q.filter(InventoryTransaction.warehouse_id == params["warehouse_id"])
        if params.get("type"):
            q = q.filter(InventoryTransaction.type == params["type"])
        if params.get("from"):
            q = q.filter(InventoryTransaction.occurred_at >= datetime.fromisoformat(params["from"]))
        if params.get("to"):
            q = q.filter(InventoryTransaction.occurred_at <= datetime.fromisoformat(params["to"]))
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        total = q.count()
        items = (q.order_by(InventoryTransaction.occurred_at.desc())
                 .offset((page - 1) * page_size).limit(page_size).all())
        return {"total": total, "page": page, "page_size": page_size,
                "items": [t.to_dict() for t in items]}


def _update_avg_cost(sku_id, warehouse_id, added_qty: int, unit_cost: float) -> None:
    snap = AvgCostSnapshot.query.filter_by(sku_id=sku_id, warehouse_id=warehouse_id).first()
    if snap is None:
        snap = AvgCostSnapshot(sku_id=sku_id, warehouse_id=warehouse_id,
                               avg_cost_usd=unit_cost, on_hand_qty=added_qty)
        db.session.add(snap)
    else:
        total_value = snap.avg_cost_usd * snap.on_hand_qty + unit_cost * added_qty
        snap.on_hand_qty += added_qty
        snap.avg_cost_usd = total_value / snap.on_hand_qty if snap.on_hand_qty else 0
        snap.updated_at = datetime.now(timezone.utc)


def _decrement_avg_cost(sku_id, warehouse_id, issued_qty: int) -> None:
    """Decrement AvgCostSnapshot.on_hand_qty when issuing from a moving-average lot."""
    snap = AvgCostSnapshot.query.filter_by(sku_id=sku_id, warehouse_id=warehouse_id).first()
    if snap is not None:
        snap.on_hand_qty = max(0, snap.on_hand_qty - issued_qty)
        snap.updated_at = datetime.now(timezone.utc)
