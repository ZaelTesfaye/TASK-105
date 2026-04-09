from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid

TICKET_TYPES = ("moderation", "report", "other")
TICKET_STATUSES = ("open", "in_progress", "closed")


class AdminTicket(db.Model):
    __tablename__ = "admin_tickets"
    __table_args__ = (
        sa.CheckConstraint(
            "type IN ('moderation', 'report', 'other')",
            name="ck_ticket_type",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'closed')",
            name="ck_ticket_status",
        ),
    )

    ticket_id = db.Column(GUID, primary_key=True, default=new_uuid)
    type = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open")
    subject = db.Column(db.String(512), nullable=False)
    body = db.Column(db.Text, nullable=False)
    target_type = db.Column(db.String(32), nullable=True)
    target_id = db.Column(db.String(36), nullable=True)
    # Nullable: system-generated tickets (safety-stock alerts) have no actor user
    created_by = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "ticket_id": str(self.ticket_id),
            "type": self.type,
            "status": self.status,
            "subject": self.subject,
            "body": self.body,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_notes": self.resolution_notes,
        }
