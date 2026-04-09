import json
from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid

TRANSACTION_TYPES = ("receipt", "issue", "transfer", "adjustment")
COSTING_METHODS = ("fifo", "moving_average")


class Warehouse(db.Model):
    __tablename__ = "warehouses"

    warehouse_id = db.Column(GUID, primary_key=True, default=new_uuid)
    community_id = db.Column(
        GUID, db.ForeignKey("communities.community_id"), nullable=True, index=True
    )
    name = db.Column(db.String(256), nullable=False)
    location = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    bins = db.relationship(
        "Bin", back_populates="warehouse", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "warehouse_id": str(self.warehouse_id),
            "community_id": str(self.community_id) if self.community_id else None,
            "name": self.name,
            "location": self.location,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }


class Bin(db.Model):
    __tablename__ = "bins"
    __table_args__ = (
        db.UniqueConstraint("warehouse_id", "bin_code", name="uix_bin_code"),
    )

    bin_id = db.Column(GUID, primary_key=True, default=new_uuid)
    warehouse_id = db.Column(
        GUID, db.ForeignKey("warehouses.warehouse_id"), nullable=False, index=True
    )
    bin_code = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=True)

    warehouse = db.relationship("Warehouse", back_populates="bins")

    def to_dict(self) -> dict:
        return {
            "bin_id": str(self.bin_id),
            "warehouse_id": str(self.warehouse_id),
            "bin_code": self.bin_code,
            "description": self.description,
        }


class InventoryLot(db.Model):
    """
    One row per (sku, warehouse, bin, lot_number) combination.

    Uniqueness enforced via expression index in migration 0002:
      uix_lot_location ON inventory_lots(sku_id, warehouse_id,
        COALESCE(bin_id,''), COALESCE(lot_number,''))
    This treats NULL bin_id / lot_number as '' for uniqueness purposes.

    Costing method is immutable once InventoryTransactions reference this lot
    (enforced by DB trigger in migration 0002: trg_lot_costing_immutable).
    """
    __tablename__ = "inventory_lots"
    __table_args__ = (
        sa.CheckConstraint(
            "costing_method IN ('fifo', 'moving_average')",
            name="ck_lot_costing_method",
        ),
        sa.CheckConstraint("on_hand_qty >= 0", name="ck_lot_qty_nonneg"),
    )

    lot_id = db.Column(GUID, primary_key=True, default=new_uuid)
    sku_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), nullable=False, index=True
    )
    warehouse_id = db.Column(
        GUID, db.ForeignKey("warehouses.warehouse_id"), nullable=False, index=True
    )
    bin_id = db.Column(GUID, db.ForeignKey("bins.bin_id"), nullable=True)
    lot_number = db.Column(db.String(128), nullable=True)
    serial_number = db.Column(db.String(128), nullable=True)
    barcode = db.Column(db.String(128), nullable=True)
    rfid = db.Column(db.String(128), nullable=True)
    # JSON array of serial strings, e.g. ["SN-1","SN-2"]
    serial_numbers = db.Column(db.Text, nullable=True)
    on_hand_qty = db.Column(db.Integer, nullable=False, default=0)
    # Immutable after first transaction (enforced by DB trigger)
    costing_method = db.Column(db.String(16), nullable=False)
    safety_stock_threshold = db.Column(db.Integer, nullable=False, default=0)
    slow_moving = db.Column(db.Boolean, nullable=False, default=False)
    # Reset only by issue transactions, not receipts (questions.md Q10)
    last_issue_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        serials = None
        if self.serial_numbers:
            try:
                serials = json.loads(self.serial_numbers)
            except json.JSONDecodeError:
                serials = self.serial_numbers
        return {
            "lot_id": str(self.lot_id),
            "sku_id": str(self.sku_id),
            "warehouse_id": str(self.warehouse_id),
            "bin_id": str(self.bin_id) if self.bin_id else None,
            "lot_number": self.lot_number,
            "barcode": self.barcode,
            "rfid": self.rfid,
            "serial_numbers": serials,
            "on_hand_qty": self.on_hand_qty,
            "costing_method": self.costing_method,
            "safety_stock_threshold": self.safety_stock_threshold,
            "slow_moving": self.slow_moving,
            "last_issue_at": self.last_issue_at.isoformat() if self.last_issue_at else None,
        }


class InventoryTransaction(db.Model):
    """
    Append-only movement ledger.  quantity_delta > 0 = inbound, < 0 = outbound.
    reason is required when type = 'adjustment' (enforced in service layer + trigger).
    """
    __tablename__ = "inventory_transactions"
    __table_args__ = (
        sa.CheckConstraint(
            "type IN ('receipt', 'issue', 'transfer', 'adjustment')",
            name="ck_inv_txn_type",
        ),
        # adjustment without a reason is a data-integrity violation
        sa.CheckConstraint(
            "type != 'adjustment' OR (reason IS NOT NULL AND reason != '')",
            name="ck_inv_txn_adjustment_reason",
        ),
    )

    transaction_id = db.Column(GUID, primary_key=True, default=new_uuid)
    type = db.Column(db.String(16), nullable=False)
    sku_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), nullable=False, index=True
    )
    warehouse_id = db.Column(
        GUID, db.ForeignKey("warehouses.warehouse_id"), nullable=False, index=True
    )
    bin_id = db.Column(GUID, db.ForeignKey("bins.bin_id"), nullable=True)
    lot_id = db.Column(GUID, db.ForeignKey("inventory_lots.lot_id"), nullable=True)
    quantity_delta = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(256), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    actor_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)
    correlation_id = db.Column(db.String(36), nullable=False)
    barcode = db.Column(db.String(128), nullable=True)
    rfid = db.Column(db.String(128), nullable=True)
    serial_numbers = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        serials = None
        if self.serial_numbers:
            try:
                serials = json.loads(self.serial_numbers)
            except json.JSONDecodeError:
                serials = self.serial_numbers
        return {
            "transaction_id": str(self.transaction_id),
            "type": self.type,
            "sku_id": str(self.sku_id),
            "warehouse_id": str(self.warehouse_id),
            "bin_id": str(self.bin_id) if self.bin_id else None,
            "lot_id": str(self.lot_id) if self.lot_id else None,
            "quantity_delta": self.quantity_delta,
            "reference": self.reference,
            "reason": self.reason,
            "actor_id": str(self.actor_id),
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
            "barcode": self.barcode,
            "rfid": self.rfid,
            "serial_numbers": serials,
        }


class CostLayer(db.Model):
    """FIFO costing layer — consumed oldest-first on issue."""
    __tablename__ = "cost_layers"
    __table_args__ = (
        sa.CheckConstraint("quantity_remaining >= 0", name="ck_cost_layer_qty"),
        sa.CheckConstraint("unit_cost_usd >= 0", name="ck_cost_layer_cost"),
        # Covering index for FIFO consumption: oldest layer first per (sku, warehouse)
        # Defined in migration 0002 as: ix_cost_layers_fifo (sku_id, warehouse_id, received_at)
    )

    layer_id = db.Column(GUID, primary_key=True, default=new_uuid)
    sku_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), nullable=False, index=True
    )
    warehouse_id = db.Column(
        GUID, db.ForeignKey("warehouses.warehouse_id"), nullable=False
    )
    quantity_remaining = db.Column(db.Integer, nullable=False)
    unit_cost_usd = db.Column(db.Float, nullable=False)
    received_at = db.Column(db.DateTime, nullable=False)


class AvgCostSnapshot(db.Model):
    """
    Moving-average cost — one row per (sku, warehouse), updated in-place on each receipt.
    Unique constraint on (sku_id, warehouse_id) ensures a single snapshot per location.
    """
    __tablename__ = "avg_cost_snapshots"
    __table_args__ = (
        db.UniqueConstraint("sku_id", "warehouse_id", name="uix_avg_cost_sku_wh"),
        sa.CheckConstraint("avg_cost_usd >= 0", name="ck_avg_cost_nonneg"),
        sa.CheckConstraint("on_hand_qty >= 0", name="ck_avg_cost_qty"),
    )

    snapshot_id = db.Column(GUID, primary_key=True, default=new_uuid)
    sku_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), nullable=False, index=True
    )
    warehouse_id = db.Column(
        GUID, db.ForeignKey("warehouses.warehouse_id"), nullable=False
    )
    avg_cost_usd = db.Column(db.Float, nullable=False)
    on_hand_qty = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class CycleCount(db.Model):
    __tablename__ = "cycle_counts"

    cycle_count_id = db.Column(GUID, primary_key=True, default=new_uuid)
    warehouse_id = db.Column(
        GUID, db.ForeignKey("warehouses.warehouse_id"), nullable=False, index=True
    )
    actor_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    counted_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    lines = db.relationship(
        "CycleCountLine",
        back_populates="cycle_count",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class CycleCountLine(db.Model):
    __tablename__ = "cycle_count_lines"
    __table_args__ = (
        # variance_reason required when variance != 0 (api-spec §6)
        sa.CheckConstraint(
            "variance = 0 OR (variance_reason IS NOT NULL AND variance_reason != '')",
            name="ck_cycle_count_variance_reason",
        ),
    )

    line_id = db.Column(GUID, primary_key=True, default=new_uuid)
    cycle_count_id = db.Column(
        GUID, db.ForeignKey("cycle_counts.cycle_count_id"), nullable=False, index=True
    )
    sku_id = db.Column(GUID, db.ForeignKey("products.product_id"), nullable=False)
    bin_id = db.Column(GUID, db.ForeignKey("bins.bin_id"), nullable=True)
    system_qty = db.Column(db.Integer, nullable=False)
    counted_qty = db.Column(db.Integer, nullable=False)
    variance = db.Column(db.Integer, nullable=False)
    variance_reason = db.Column(db.Text, nullable=True)

    cycle_count = db.relationship("CycleCount", back_populates="lines")

    def to_dict(self) -> dict:
        return {
            "sku_id": str(self.sku_id),
            "bin_id": str(self.bin_id) if self.bin_id else None,
            "system_qty": self.system_qty,
            "counted_qty": self.counted_qty,
            "variance": self.variance,
            "variance_reason": self.variance_reason,
        }


class SkuCostingPolicy(db.Model):
    """
    Enforces costing method immutability at the SKU level (not just per lot).
    The first inventory receipt for a SKU establishes the policy; any subsequent
    receipt using a different method is rejected with 422 costing_method_locked.
    """
    __tablename__ = "sku_costing_policies"

    sku_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), primary_key=True, nullable=False
    )
    costing_method = db.Column(db.String(32), nullable=False)
    locked_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
