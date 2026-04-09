"""
Unit tests for InventoryService and helper functions.
All calls go directly to the service / helper layer, no HTTP.

Covered:
  - FIFO partial and multi-layer consumption
  - FIFO insufficient-stock guard
  - Moving-average cost calculation on receipt
  - Decrement of AvgCostSnapshot on issue
  - No-underflow guard for avg-cost decrement
  - _current_cost_usd for FIFO and moving-average lots
  - Transfer carries the source unit cost to the destination lot
  - Costing-method immutability after first transaction
  - Adjustment requires a reason field
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.services.inventory_service import (
    InventoryService,
    _consume_fifo_layers,
    _update_avg_cost,
    _decrement_avg_cost,
    _current_cost_usd,
)
from app.models.inventory import (
    InventoryLot,
    CostLayer,
    AvgCostSnapshot,
)
from app.models.catalog import Product
from app.models.inventory import Warehouse
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_warehouse(suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    wh = Warehouse(name=f"WH-{suffix}", location=f"Location-{suffix}")
    db.session.add(wh)
    db.session.flush()
    return wh


def _make_product(suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    p = Product(
        sku=f"SKU-{suffix}",
        name=f"Product {suffix}",
        brand="TestBrand",
        category="TestCat",
        price_usd=9.99,
    )
    db.session.add(p)
    db.session.flush()
    return p


def _make_actor(app, suffix=None):
    """Register and return a User for use as an actor."""
    from app.services.auth_service import AuthService
    suffix = suffix or uuid.uuid4().hex[:8]
    return AuthService.register(f"inv_actor_{suffix}", "ActorPass1234!")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# FIFO layer consumption
# ---------------------------------------------------------------------------

class TestFifoConsumption:

    def test_fifo_partial_consumption(self, app):
        """Receipt 10 units, issue 3 → the single FIFO layer has 7 remaining."""
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 10,
                "unit_cost_usd": 5.0,
                "costing_method": "fifo",
                "occurred_at": _now_iso(),
            }, actor)

            InventoryService.record_issue({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 3,
                "occurred_at": _now_iso(),
            }, actor)

            layer = CostLayer.query.filter_by(
                sku_id=prod.product_id, warehouse_id=wh.warehouse_id
            ).first()
            assert layer.quantity_remaining == 7

    def test_fifo_multi_layer_consumption(self, app):
        """Two receipts (5 each), issue 7 → first layer fully consumed, second has 3 remaining."""
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            t1 = "2024-01-01T00:00:00"
            t2 = "2024-01-02T00:00:00"

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 5,
                "unit_cost_usd": 10.0,
                "costing_method": "fifo",
                "occurred_at": t1,
            }, actor)

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 5,
                "unit_cost_usd": 20.0,
                "costing_method": "fifo",
                "occurred_at": t2,
            }, actor)

            InventoryService.record_issue({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 7,
                "occurred_at": _now_iso(),
            }, actor)

            layers = (
                CostLayer.query
                .filter_by(sku_id=prod.product_id, warehouse_id=wh.warehouse_id)
                .order_by(CostLayer.received_at.asc())
                .all()
            )
            assert len(layers) == 2
            assert layers[0].quantity_remaining == 0   # first layer fully consumed
            assert layers[1].quantity_remaining == 3   # 5 - 2 = 3

    def test_fifo_insufficient_stock_raises(self, app):
        """record_issue raises UnprocessableError(error='insufficient_stock') when qty > on_hand."""
        from app.errors import UnprocessableError
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 5,
                "unit_cost_usd": 10.0,
                "costing_method": "fifo",
                "occurred_at": _now_iso(),
            }, actor)

            with pytest.raises(UnprocessableError) as exc_info:
                InventoryService.record_issue({
                    "sku_id": str(prod.product_id),
                    "warehouse_id": str(wh.warehouse_id),
                    "quantity": 99,
                    "occurred_at": _now_iso(),
                }, actor)
            assert exc_info.value.error == "insufficient_stock"


# ---------------------------------------------------------------------------
# Moving-average costing
# ---------------------------------------------------------------------------

class TestMovingAverageCost:

    def test_moving_average_cost_computed(self, app):
        """
        Receipt 10 @ $10 then receipt 10 @ $20 → avg_cost = $15, on_hand = 20.
        """
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 10,
                "unit_cost_usd": 10.0,
                "costing_method": "moving_average",
                "occurred_at": _now_iso(),
            }, actor)

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 10,
                "unit_cost_usd": 20.0,
                "costing_method": "moving_average",
                "occurred_at": _now_iso(),
            }, actor)

            snap = AvgCostSnapshot.query.filter_by(
                sku_id=prod.product_id, warehouse_id=wh.warehouse_id
            ).first()
            assert snap is not None
            assert snap.on_hand_qty == 20
            assert abs(snap.avg_cost_usd - 15.0) < 1e-6

    def test_decrement_avg_cost_on_issue(self, app):
        """After issuing 5 from an MA lot with 20 on hand, snapshot.on_hand_qty == 15."""
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 20,
                "unit_cost_usd": 10.0,
                "costing_method": "moving_average",
                "occurred_at": _now_iso(),
            }, actor)

            InventoryService.record_issue({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 5,
                "occurred_at": _now_iso(),
            }, actor)

            snap = AvgCostSnapshot.query.filter_by(
                sku_id=prod.product_id, warehouse_id=wh.warehouse_id
            ).first()
            assert snap.on_hand_qty == 15

    def test_decrement_avg_cost_no_underflow(self, app):
        """Issuing all stock leaves on_hand_qty == 0, never negative."""
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 10,
                "unit_cost_usd": 5.0,
                "costing_method": "moving_average",
                "occurred_at": _now_iso(),
            }, actor)

            InventoryService.record_issue({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 10,
                "occurred_at": _now_iso(),
            }, actor)

            snap = AvgCostSnapshot.query.filter_by(
                sku_id=prod.product_id, warehouse_id=wh.warehouse_id
            ).first()
            assert snap.on_hand_qty == 0


# ---------------------------------------------------------------------------
# _current_cost_usd helper
# ---------------------------------------------------------------------------

class TestCurrentCostUsd:

    def test_current_cost_fifo(self, app):
        """_current_cost_usd returns the weighted average of remaining FIFO layers."""
        with app.app_context():
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            # Two layers: 4 units @ $10 and 6 units @ $20 → weighted avg = (40+120)/10 = $16
            db.session.add(CostLayer(
                sku_id=prod.product_id,
                warehouse_id=wh.warehouse_id,
                quantity_remaining=4,
                unit_cost_usd=10.0,
                received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ))
            db.session.add(CostLayer(
                sku_id=prod.product_id,
                warehouse_id=wh.warehouse_id,
                quantity_remaining=6,
                unit_cost_usd=20.0,
                received_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            ))
            db.session.commit()

            cost = _current_cost_usd(prod.product_id, wh.warehouse_id, "fifo")
            assert abs(cost - 16.0) < 1e-4

    def test_current_cost_ma(self, app):
        """_current_cost_usd returns snap.avg_cost_usd for a moving_average lot."""
        with app.app_context():
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            snap = AvgCostSnapshot(
                sku_id=prod.product_id,
                warehouse_id=wh.warehouse_id,
                avg_cost_usd=12.50,
                on_hand_qty=100,
            )
            db.session.add(snap)
            db.session.commit()

            cost = _current_cost_usd(prod.product_id, wh.warehouse_id, "moving_average")
            assert abs(cost - 12.50) < 1e-6


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------

class TestTransfer:

    def test_transfer_carries_cost(self, app):
        """
        record_transfer creates a destination receipt whose unit_cost_usd matches
        the source lot's unit cost, not zero.
        """
        with app.app_context():
            actor = _make_actor(app)
            wh_src = _make_warehouse()
            wh_dst = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            unit_cost = 25.0
            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh_src.warehouse_id),
                "quantity": 10,
                "unit_cost_usd": unit_cost,
                "costing_method": "fifo",
                "occurred_at": _now_iso(),
            }, actor)

            InventoryService.record_transfer({
                "sku_id": str(prod.product_id),
                "from_warehouse_id": str(wh_src.warehouse_id),
                "to_warehouse_id": str(wh_dst.warehouse_id),
                "quantity": 4,
            }, actor)

            dst_layer = CostLayer.query.filter_by(
                sku_id=prod.product_id, warehouse_id=wh_dst.warehouse_id
            ).first()
            assert dst_layer is not None
            assert abs(dst_layer.unit_cost_usd - unit_cost) < 1e-6


# ---------------------------------------------------------------------------
# Costing-method immutability
# ---------------------------------------------------------------------------

class TestCostingMethodLocked:

    def test_costing_method_locked(self, app):
        """
        After the first transaction, attempting a receipt with a different
        costing_method raises UnprocessableError(error='costing_method_locked').
        """
        from app.errors import UnprocessableError
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 5,
                "unit_cost_usd": 10.0,
                "costing_method": "fifo",
                "occurred_at": _now_iso(),
            }, actor)

            with pytest.raises(UnprocessableError) as exc_info:
                InventoryService.record_receipt({
                    "sku_id": str(prod.product_id),
                    "warehouse_id": str(wh.warehouse_id),
                    "quantity": 5,
                    "unit_cost_usd": 10.0,
                    "costing_method": "moving_average",
                    "occurred_at": _now_iso(),
                }, actor)
            assert exc_info.value.error == "costing_method_locked"


# ---------------------------------------------------------------------------
# Adjustment
# ---------------------------------------------------------------------------

class TestAdjustment:

    def test_adjustment_requires_reason(self, app):
        """record_adjustment raises AppError when the 'reason' field is absent."""
        from app.errors import AppError
        with app.app_context():
            actor = _make_actor(app)
            wh = _make_warehouse()
            prod = _make_product()
            db.session.commit()

            # Create a lot first
            InventoryService.record_receipt({
                "sku_id": str(prod.product_id),
                "warehouse_id": str(wh.warehouse_id),
                "quantity": 10,
                "unit_cost_usd": 5.0,
                "costing_method": "fifo",
                "occurred_at": _now_iso(),
            }, actor)

            with pytest.raises(AppError) as exc_info:
                InventoryService.record_adjustment({
                    "sku_id": str(prod.product_id),
                    "warehouse_id": str(wh.warehouse_id),
                    "quantity_delta": -2,
                    # "reason" intentionally omitted
                }, actor)
            assert exc_info.value.error == "reason_required"
