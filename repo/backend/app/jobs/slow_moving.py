"""
Daily 02:00 UTC: flag inventory lots where no issue has occurred for 60+ days.
Only outbound movements (issues) reset the timer — receipts do not.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from flask import g

from app.extensions import db
from app.models.inventory import InventoryLot

logger = logging.getLogger(__name__)
_SLOW_MOVING_DAYS = 60


def flag_slow_moving() -> None:
    cid = getattr(g, "correlation_id", "")
    cutoff = datetime.now(timezone.utc) - timedelta(days=_SLOW_MOVING_DAYS)

    flagged = InventoryLot.query.filter(
        db.or_(
            InventoryLot.last_issue_at < cutoff,
            db.and_(
                InventoryLot.last_issue_at.is_(None),
                InventoryLot.created_at < cutoff,
            ),
        )
    ).all()

    count = 0
    for lot in flagged:
        if not lot.slow_moving:
            lot.slow_moving = True
            count += 1

    db.session.commit()
    logger.info(json.dumps({"event": "slow_moving_flag", "newly_flagged": count, "correlation_id": cid}))
