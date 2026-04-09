from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid

MESSAGE_TYPES = ("text", "image_meta", "file_meta", "emoji", "system")
RECEIPT_STATUSES = ("sent", "delivered", "read")
# Monotonic status ordering — transitions may only advance
RECEIPT_STATUS_ORDER = {"sent": 0, "delivered": 1, "read": 2}


class Message(db.Model):
    __tablename__ = "messages"
    __table_args__ = (
        sa.CheckConstraint(
            "type IN ('text', 'image_meta', 'file_meta', 'emoji', 'system')",
            name="ck_message_type",
        ),
        # exactly one target: direct XOR group (system messages may have neither)
        sa.CheckConstraint(
            "NOT (recipient_id IS NOT NULL AND group_id IS NOT NULL)",
            name="ck_message_single_target",
        ),
    )

    message_id = db.Column(GUID, primary_key=True, default=new_uuid)
    type = db.Column(db.String(16), nullable=False)
    sender_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    # direct message target
    recipient_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=True)
    # group message target (community)
    group_id = db.Column(GUID, db.ForeignKey("communities.community_id"), nullable=True)
    # body excluded from all log output by StructuredLogMiddleware
    body = db.Column(db.Text, nullable=True)
    # JSON: {filename, mime_type, size_bytes}  — metadata only, no file bytes stored
    file_metadata = db.Column(db.Text, nullable=True)
    sent_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    # sent_at + 7 days; offline queue purge threshold
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    correlation_id = db.Column(db.String(36), nullable=False)

    receipts = db.relationship(
        "MessageReceipt",
        back_populates="message",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        import json
        return {
            "message_id": str(self.message_id),
            "type": self.type,
            "sender_id": str(self.sender_id),
            "recipient_id": str(self.recipient_id) if self.recipient_id else None,
            "group_id": str(self.group_id) if self.group_id else None,
            "body": self.body,
            "file_metadata": json.loads(self.file_metadata) if self.file_metadata else None,
            "sent_at": self.sent_at.isoformat(),
        }


class MessageReceipt(db.Model):
    """
    One receipt row per (message, recipient) — unique constraint prevents duplicates.
    The status progression is: sent → delivered → read (never reverses).
    """
    __tablename__ = "message_receipts"
    __table_args__ = (
        # One receipt per (message, recipient) — prevents duplicate delivery records
        db.UniqueConstraint("message_id", "recipient_id", name="uix_receipt_msg_recipient"),
        sa.CheckConstraint(
            "status IN ('sent', 'delivered', 'read')",
            name="ck_receipt_status",
        ),
    )

    receipt_id = db.Column(GUID, primary_key=True, default=new_uuid)
    message_id = db.Column(
        GUID, db.ForeignKey("messages.message_id"), nullable=False, index=True
    )
    recipient_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="sent")
    updated_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # Exponential backoff tracking for offline redelivery
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    next_retry_at = db.Column(db.DateTime, nullable=True)

    message = db.relationship("Message", back_populates="receipts")

    def to_dict(self) -> dict:
        return {
            "receipt_id": str(self.receipt_id),
            "message_id": str(self.message_id),
            "recipient_id": str(self.recipient_id),
            "status": self.status,
            "updated_at": self.updated_at.isoformat(),
        }
