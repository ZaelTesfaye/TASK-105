"""Messaging service (REST fallback; WebSocket handled in app/websocket.py)."""
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.messaging import Message, MessageReceipt, MESSAGE_TYPES, RECEIPT_STATUS_ORDER
from app.models.user import User
from app.errors import NotFoundError, AppError, ConflictError, ForbiddenError

_OFFLINE_TTL_DAYS = 7


class MessagingService:

    @staticmethod
    def send_message(data: dict, sender: User) -> Message:
        """Create a message and initial receipt (called from WebSocket and REST)."""
        msg_type = data.get("type", "text")
        if msg_type not in MESSAGE_TYPES:
            raise AppError("invalid_message_type",
                           f"type must be one of: {', '.join(MESSAGE_TYPES)}",
                           field="type", status_code=400)

        recipient_id = data.get("recipient_id")
        group_id = data.get("group_id")
        if recipient_id and group_id:
            raise AppError("ambiguous_target",
                           "Specify recipient_id or group_id, not both",
                           status_code=400)

        expires_at = datetime.now(timezone.utc) + timedelta(days=_OFFLINE_TTL_DAYS)
        msg = Message(
            type=msg_type,
            sender_id=sender.user_id,
            recipient_id=recipient_id,
            group_id=group_id,
            body=data.get("body"),
            file_metadata=data.get("file_metadata"),
            expires_at=expires_at,
            correlation_id=data.get("correlation_id", ""),
        )
        db.session.add(msg)
        db.session.flush()

        # Create delivery receipts: one for direct; one per member for group
        if recipient_id:
            db.session.add(MessageReceipt(
                message_id=msg.message_id,
                recipient_id=recipient_id,
                status="sent",
            ))
        elif group_id:
            from app.models.community import CommunityMember
            from app.services.community_service import CommunityService
            # Sender must be an active member of the community
            membership = CommunityMember.query.filter_by(
                community_id=group_id, user_id=sender.user_id, left_at=None
            ).first()
            if membership is None:
                raise ForbiddenError(
                    "not_community_member",
                    "You must be an active member of this community to send group messages",
                )
            member_ids = CommunityService.get_active_member_ids(group_id)
            for mid in member_ids:
                if mid != str(sender.user_id):
                    db.session.add(MessageReceipt(
                        message_id=msg.message_id,
                        recipient_id=mid,
                        status="sent",
                    ))

        db.session.commit()
        return msg

    @staticmethod
    def get_queued(user: User) -> list:
        """Return undelivered messages for this user (status='sent', not expired)."""
        receipts = (
            MessageReceipt.query
            .filter_by(recipient_id=user.user_id, status="sent")
            .join(Message)
            .filter(Message.expires_at > datetime.now(timezone.utc))
            .all()
        )
        return [r.message.to_dict() for r in receipts]

    @staticmethod
    def update_receipt(message_id: str, status: str, user: User) -> dict:
        """Advance a receipt status (sent → delivered → read, never backward)."""
        if status not in ("delivered", "read"):
            raise AppError("invalid_status", "status must be 'delivered' or 'read'",
                           field="status", status_code=400)
        receipt = MessageReceipt.query.filter_by(
            message_id=message_id, recipient_id=user.user_id
        ).first()
        if receipt is None:
            raise NotFoundError("message_receipt")

        current_order = RECEIPT_STATUS_ORDER.get(receipt.status, 0)
        new_order = RECEIPT_STATUS_ORDER.get(status, 0)
        if new_order <= current_order:
            raise ConflictError(
                "status_regression",
                f"Cannot transition from '{receipt.status}' to '{status}'",
            )

        receipt.status = status
        receipt.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        msg = receipt.message.to_dict()
        msg["delivery_status"] = status
        return msg
