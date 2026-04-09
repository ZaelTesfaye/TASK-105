"""
WebSocket / STOMP messaging endpoints.
Flask-SocketIO is used as the STOMP-compatible transport.
Authentication uses the Bearer token from the STOMP CONNECT frame headers.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from flask_socketio import emit, join_room, disconnect
from flask import request, g

from app.extensions import socketio, db
from app.services.messaging_service import MessagingService

logger = logging.getLogger(__name__)


# sid → (user, token_hash) mapping; populated on connect, cleaned up on disconnect
_sid_user_map: dict = {}


@socketio.on("connect", namespace="/ws/messaging")
def on_connect(auth):
    g.correlation_id = f"ws-connect-{uuid.uuid4()}"
    token = (auth or {}).get("token", "")
    user = _load_user(token)
    if user is None:
        logger.info('{"event":"ws_connect_rejected","correlation_id":"%s"}' % g.correlation_id)
        disconnect()
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _sid_user_map[request.sid] = (user, token_hash)
    # Join personal room for direct message delivery
    join_room(f"user_{user.user_id}")
    # Join community rooms for group message delivery
    from app.models.community import CommunityMember
    memberships = CommunityMember.query.filter_by(
        user_id=user.user_id, left_at=None
    ).all()
    for m in memberships:
        join_room(f"community_{m.community_id}")


@socketio.on("disconnect", namespace="/ws/messaging")
def on_disconnect():
    _sid_user_map.pop(request.sid, None)


def _get_authenticated_user():
    """Return the user for the current sid, re-validating the session token."""
    entry = _sid_user_map.get(request.sid)
    if entry is None:
        return None
    user, token_hash = entry
    from app.models.user import Session
    session = db.session.get(Session, token_hash)
    if session is None:
        return None
    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        _sid_user_map.pop(request.sid, None)
        disconnect()
        return None
    return user


@socketio.on("direct", namespace="/ws/messaging")
def on_direct(data):
    g.correlation_id = f"ws-direct-{uuid.uuid4()}"
    user = _get_authenticated_user()
    if user is None:
        return
    data["correlation_id"] = g.correlation_id
    msg = MessagingService.send_message(data, sender=user)
    emit("message", msg.to_dict(), room=f"user_{data.get('recipient_id')}")


@socketio.on("group", namespace="/ws/messaging")
def on_group(data):
    g.correlation_id = f"ws-group-{uuid.uuid4()}"
    user = _get_authenticated_user()
    if user is None:
        return
    data["correlation_id"] = g.correlation_id
    msg = MessagingService.send_message(data, sender=user)
    emit("message", msg.to_dict(), room=f"community_{data.get('group_id')}")


@socketio.on("receipt", namespace="/ws/messaging")
def on_receipt(data):
    g.correlation_id = f"ws-receipt-{uuid.uuid4()}"
    user = _get_authenticated_user()
    if user is None:
        return
    MessagingService.update_receipt(data["message_id"], data["status"], user=user)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_user(token: str):
    """Load user from raw token string without touching the HTTP request object."""
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    from app.models.user import Session, User
    session = db.session.get(Session, token_hash)
    if session is None:
        return None
    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    user = db.session.get(User, session.user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user
