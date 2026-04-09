"""
Every 10 minutes: flag SKUs where on_hand_qty < safety_stock_threshold.
Creates an AdminTicket of type 'report' if one isn't already open for the SKU.
"""
import json
import logging

from flask import g

from app.extensions import db
from app.models.inventory import InventoryLot
from app.models.admin import AdminTicket

logger = logging.getLogger(__name__)


def _cid() -> str:
    return getattr(g, "correlation_id", "")


def check_safety_stock() -> None:
    cid = _cid()
    below = InventoryLot.query.filter(
        InventoryLot.on_hand_qty < InventoryLot.safety_stock_threshold,
        InventoryLot.safety_stock_threshold > 0,
    ).all()

    for lot in below:
        subject = f"Safety stock alert: SKU {lot.sku_id}"
        existing = AdminTicket.query.filter_by(
            type="report", subject=subject, status="open"
        ).first()
        if existing is None:
            ticket = AdminTicket(
                type="report",
                subject=subject,
                body=f"on_hand_qty={lot.on_hand_qty} < threshold={lot.safety_stock_threshold}",
                target_type="inventory_lot",
                target_id=str(lot.lot_id),
                created_by=None,  # system-generated
            )
            db.session.add(ticket)
            logger.warning(json.dumps({"event": "safety_stock_alert",
                                       "sku_id": str(lot.sku_id),
                                       "lot_id": str(lot.lot_id),
                                       "correlation_id": cid}))

    db.session.commit()
