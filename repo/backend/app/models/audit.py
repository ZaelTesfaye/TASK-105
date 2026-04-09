from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid

AUDIT_ACTION_TYPES = ("settlement", "moderation", "inventory", "auth", "content", "template")


class AuditLog(db.Model):
    """
    Append-only audit log.
    DB triggers (migration 0001) prevent UPDATE and DELETE on this table.
    Sensitive fields are redacted in before_state / after_state before insertion.
    """
    __tablename__ = "audit_log"
    __table_args__ = (
        sa.CheckConstraint(
            "action_type IN ('settlement', 'moderation', 'inventory', 'auth', 'content', 'template')",
            name="ck_audit_action_type",
        ),
    )

    log_id = db.Column(GUID, primary_key=True, default=new_uuid)
    action_type = db.Column(db.String(32), nullable=False, index=True)
    # Nullable: system-initiated events (e.g. job-triggered) may have no actor
    actor_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=True)
    target_type = db.Column(db.String(64), nullable=False)
    target_id = db.Column(db.String(36), nullable=False)
    before_state = db.Column(db.Text, nullable=True)  # JSON snapshot, sensitive fields redacted
    after_state = db.Column(db.Text, nullable=True)   # JSON snapshot
    occurred_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    correlation_id = db.Column(db.String(36), nullable=False)

    def to_dict(self) -> dict:
        import json
        return {
            "log_id": str(self.log_id),
            "action_type": self.action_type,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "before": json.loads(self.before_state) if self.before_state else None,
            "after": json.loads(self.after_state) if self.after_state else None,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
        }


class JobLock(db.Model):
    """Advisory lock rows for background jobs — prevents concurrent execution."""
    __tablename__ = "job_locks"

    job_name = db.Column(db.String(64), primary_key=True)
    locked_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    locked_by = db.Column(db.String(64), nullable=False, default="scheduler")
