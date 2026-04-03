"""
Retries undelivered messages with exponential backoff.
Purges messages past their 7-day expiry.

Backoff schedule (capped at 2 hours):
  attempt 0 → retry immediately
  attempt 1 → 60 s
  attempt 2 → 120 s
  attempt 3 → 240 s
  …
  attempt N → min(60 * 2^N, 7200) s
"""
import logging
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.messaging import Message, MessageReceipt

logger = logging.getLogger(__name__)

_MAX_BACKOFF_SECONDS = 7200  # 2 hours


def _next_retry_delay(retry_count: int) -> int:
    """Return backoff in seconds for the given attempt number."""
    return min(60 * (2 ** retry_count), _MAX_BACKOFF_SECONDS)


def redeliver_messages() -> None:
    now = datetime.now(timezone.utc)

    # 1. Purge expired messages (cascades to receipts via DB constraint)
    expired = Message.query.filter(Message.expires_at < now).all()
    for msg in expired:
        db.session.delete(msg)
    if expired:
        db.session.commit()
        logger.info({"event": "message_purge", "count": len(expired)})

    # 2. Redeliver pending receipts that are due (next_retry_at IS NULL or <= now)
    pending = (
        MessageReceipt.query
        .filter(
            MessageReceipt.status == "sent",
            db.or_(
                MessageReceipt.next_retry_at.is_(None),
                MessageReceipt.next_retry_at <= now,
            ),
        )
        .join(Message)
        .filter(Message.expires_at >= now)
        .all()
    )

    delivered = 0
    for receipt in pending:
        try:
            # Push via Socket.IO (existing behaviour)
            from app.extensions import socketio
            socketio.emit(
                "message",
                receipt.message.to_dict(),
                room=f"user_{receipt.recipient_id}",
                namespace="/ws/messaging",
            )

            # Push via STOMP registry (if recipient has an active STOMP session)
            try:
                from app.stomp_ws import stomp_registry, _build_frame
                import json as _json
                if stomp_registry.is_user_online(str(receipt.recipient_id)):
                    frame = _build_frame("MESSAGE", {
                        "destination": "/user/queue/messages",
                        "content-type": "application/json",
                        "message-id": str(receipt.message_id),
                    }, _json.dumps(receipt.message.to_dict()))
                    stomp_registry.push_to_user(str(receipt.recipient_id), frame)
            except ImportError:
                pass  # flask-sock not installed

            delivered += 1
            logger.info({"event": "message_redelivery",
                         "message_id": str(receipt.message_id),
                         "attempt": receipt.retry_count})
        except Exception as exc:
            logger.warning({"event": "redelivery_error",
                            "message_id": str(receipt.message_id),
                            "error": str(exc)})

        # Advance backoff regardless of success/failure
        receipt.retry_count += 1
        delay = _next_retry_delay(receipt.retry_count)
        receipt.next_retry_at = now + timedelta(seconds=delay)

    if pending:
        db.session.commit()

    logger.info({"event": "redelivery_run", "attempted": len(pending), "emitted": delivered})
