from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid

SETTLEMENT_STATUSES = ("pending", "processing", "completed", "disputed", "cancelled")
SETTLEMENT_CYCLES = ("weekly", "biweekly")
DISPUTE_STATUSES = ("open", "resolved", "rejected")


class CommissionRule(db.Model):
    __tablename__ = "commission_rules"
    __table_args__ = (
        # rate bounds: 0 ≤ floor ≤ rate ≤ ceiling ≤ 15  (questions.md Q3 / api-spec §4)
        sa.CheckConstraint(
            "floor >= 0 AND ceiling <= 15 AND floor <= rate AND rate <= ceiling",
            name="ck_commission_rate_bounds",
        ),
        sa.CheckConstraint(
            "settlement_cycle IN ('weekly', 'biweekly')",
            name="ck_commission_cycle",
        ),
    )

    rule_id = db.Column(GUID, primary_key=True, default=new_uuid)
    community_id = db.Column(
        GUID, db.ForeignKey("communities.community_id"), nullable=False, index=True
    )
    # NULL = community-default rule; category_rule > community_default > system_default 6%
    product_category = db.Column(db.String(128), nullable=True)
    rate = db.Column(db.Float, nullable=False, default=6.0)
    floor = db.Column(db.Float, nullable=False, default=0.0)
    ceiling = db.Column(db.Float, nullable=False, default=15.0)
    settlement_cycle = db.Column(db.String(16), nullable=False, default="weekly")
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "rule_id": str(self.rule_id),
            "community_id": str(self.community_id),
            "product_category": self.product_category,
            "rate": self.rate,
            "floor": self.floor,
            "ceiling": self.ceiling,
            "settlement_cycle": self.settlement_cycle,
        }


class SettlementRun(db.Model):
    __tablename__ = "settlement_runs"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'disputed', 'cancelled')",
            name="ck_settlement_status",
        ),
        # period sanity check
        sa.CheckConstraint("period_end >= period_start", name="ck_settlement_period"),
    )

    settlement_id = db.Column(GUID, primary_key=True, default=new_uuid)
    community_id = db.Column(
        GUID, db.ForeignKey("communities.community_id"), nullable=False, index=True
    )
    # Unique idempotency key prevents duplicate settlement runs (questions.md Q5)
    idempotency_key = db.Column(db.String(256), unique=True, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    total_order_value = db.Column(db.Float, nullable=False, default=0.0)
    commission_amount = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finalized_at = db.Column(db.DateTime, nullable=True)

    disputes = db.relationship(
        "SettlementDispute", back_populates="settlement", lazy="dynamic"
    )

    def to_dict(self) -> dict:
        return {
            "settlement_id": str(self.settlement_id),
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "community_id": str(self.community_id),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_order_value_usd": self.total_order_value,
            "commission_amount_usd": self.commission_amount,
            "created_at": self.created_at.isoformat(),
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
        }


class SettlementDispute(db.Model):
    __tablename__ = "settlement_disputes"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'rejected')",
            name="ck_dispute_status",
        ),
        # disputes can only be filed against non-negative amounts
        sa.CheckConstraint("disputed_amount >= 0", name="ck_dispute_amount"),
    )

    dispute_id = db.Column(GUID, primary_key=True, default=new_uuid)
    settlement_id = db.Column(
        GUID, db.ForeignKey("settlement_runs.settlement_id"), nullable=False, index=True
    )
    filed_by = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    disputed_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open")
    resolution_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    resolved_at = db.Column(db.DateTime, nullable=True)

    settlement = db.relationship("SettlementRun", back_populates="disputes")

    def to_dict(self) -> dict:
        return {
            "dispute_id": str(self.dispute_id),
            "settlement_id": str(self.settlement_id),
            "filed_by": str(self.filed_by),
            "reason": self.reason,
            "disputed_amount": self.disputed_amount,
            "status": self.status,
            "resolution_notes": self.resolution_notes,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
