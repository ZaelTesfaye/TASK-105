"""
API functional tests for WebSocket/STOMP messaging (WS-1 gap fix).

Uses flask_socketio.SocketIOTestClient to exercise the /ws/messaging namespace
directly — no HTTP; real event handlers, real DB, real service calls.

All WebSocket operations (connect, emit, receive) run inside
``with app.app_context()`` because Flask-SocketIO's test client
executes event handlers synchronously in the same thread; the app context
keeps the SQLAlchemy session alive so handlers can see committed rows.

The tests reuse the session-scoped ``app`` fixture from conftest.py to avoid
calling socketio.init_app() more than once per pytest session.

Covered:
  - connect with valid token → is_connected True
  - connect with invalid/missing token → rejected (not connected)
  - on_direct: send direct message → recipient's room receives 'message' event
  - on_group: send group message → community room receives 'message' event
  - on_receipt: acknowledge delivery/read → receipt status advanced in DB
  - disconnect: _sid_user_map cleaned up (no stale entry)
  - token expiry mid-connection: expired token → disconnect on next event
"""
import uuid
import hashlib
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db as _db, socketio
from app.services.auth_service import AuthService
from app.services.community_service import CommunityService
from app.models.user import Session
from app.models.messaging import MessageReceipt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_user(app, role="Member"):
    """Register + login a fresh user; return (user_id_str, raw_token)."""
    suffix = uuid.uuid4().hex[:8]
    username = f"ws_{suffix}"
    with app.app_context():
        AuthService.register(username, "WsTestPass12!", role=role)
        result = AuthService.login(username, "WsTestPass12!")
    return result["user_id"], result["token"]


def _connect(app, token):
    """Return a connected SocketIOTestClient for /ws/messaging.
    Must be called within an active app_context."""
    return socketio.test_client(
        app, namespace="/ws/messaging", auth={"token": token}
    )


# ---------------------------------------------------------------------------
# Connection / authentication
# ---------------------------------------------------------------------------

class TestWsConnect:

    def test_connect_valid_token(self, app):
        """A valid Bearer token results in a successful WebSocket connection."""
        uid_a, tok_a = _new_user(app)
        with app.app_context():
            ws = _connect(app, tok_a)
            assert ws.is_connected("/ws/messaging")
            ws.disconnect("/ws/messaging")

    def test_connect_invalid_token_rejected(self, app):
        """An invalid token causes the server to disconnect immediately."""
        with app.app_context():
            ws = _connect(app, "notarealtoken123456")
            assert not ws.is_connected("/ws/messaging")

    def test_connect_empty_token_rejected(self, app):
        """An empty token causes the server to disconnect immediately."""
        with app.app_context():
            ws = _connect(app, "")
            assert not ws.is_connected("/ws/messaging")

    def test_disconnect_cleans_up(self, app):
        """After explicit disconnect, _sid_user_map no longer has an entry for the user."""
        from app import websocket as ws_mod
        uid_a, tok_a = _new_user(app)
        with app.app_context():
            ws = _connect(app, tok_a)
            assert ws.is_connected("/ws/messaging")
            assert any(
                str(u.user_id) == uid_a
                for u, _ in ws_mod._sid_user_map.values()
            ), f"User {uid_a} not found in sid_map"
            ws.disconnect("/ws/messaging")
            assert not any(
                str(u.user_id) == uid_a
                for u, _ in ws_mod._sid_user_map.values()
            ), f"User {uid_a} still in sid_map after disconnect"


# ---------------------------------------------------------------------------
# Direct messaging (on_direct)
# ---------------------------------------------------------------------------

class TestWsDirect:

    def test_direct_message_emitted_to_recipient_room(self, app):
        """Sending 'direct' from user A delivers a 'message' event to user B's socket."""
        uid_a, tok_a = _new_user(app)
        uid_b, tok_b = _new_user(app)

        with app.app_context():
            ws_a = _connect(app, tok_a)
            ws_b = _connect(app, tok_b)

            ws_a.emit(
                "direct",
                {"type": "text", "recipient_id": uid_b, "body": "Hello from A"},
                namespace="/ws/messaging",
            )

            received_b = ws_b.get_received("/ws/messaging")
            assert any(evt["name"] == "message" for evt in received_b), \
                f"Recipient did not receive 'message' event; got: {received_b}"

            ws_a.disconnect("/ws/messaging")
            ws_b.disconnect("/ws/messaging")

    def test_direct_message_persisted_as_receipt(self, app):
        """After a 'direct' event, a MessageReceipt row is written with status='sent'."""
        uid_a, tok_a = _new_user(app)
        uid_b, tok_b = _new_user(app)

        with app.app_context():
            ws_a = _connect(app, tok_a)

            ws_a.emit(
                "direct",
                {"type": "text", "recipient_id": uid_b, "body": "Persist check"},
                namespace="/ws/messaging",
            )

            receipts = MessageReceipt.query.filter_by(recipient_id=uid_b).all()
            assert len(receipts) >= 1
            assert receipts[-1].status == "sent"

            ws_a.disconnect("/ws/messaging")

    def test_direct_message_body_in_event(self, app):
        """The emitted 'message' event payload contains the sent body and sender_id."""
        uid_a, tok_a = _new_user(app)
        uid_b, tok_b = _new_user(app)

        with app.app_context():
            ws_b = _connect(app, tok_b)
            ws_a = _connect(app, tok_a)

            ws_a.emit(
                "direct",
                {"type": "text", "recipient_id": uid_b, "body": "unique_body_xyz"},
                namespace="/ws/messaging",
            )

            events = ws_b.get_received("/ws/messaging")
            message_events = [e for e in events if e["name"] == "message"]
            assert message_events, "No 'message' event received"
            payload = message_events[-1]["args"]
            if isinstance(payload, list):
                payload = payload[0]
            assert payload.get("body") == "unique_body_xyz"
            assert payload.get("sender_id") == uid_a

            ws_a.disconnect("/ws/messaging")
            ws_b.disconnect("/ws/messaging")


# ---------------------------------------------------------------------------
# Group messaging (on_group)
# ---------------------------------------------------------------------------

class TestWsGroup:

    def test_group_message_delivered_to_community_room(self, app):
        """Sending 'group' emits a 'message' event to the community room.
        A member connected before the send receives the event."""
        uid_admin, tok_admin = _new_user(app, role="Administrator")
        uid_member, tok_member = _new_user(app)

        with app.app_context():
            comm = CommunityService.create({
                "name": f"WS Comm {uuid.uuid4().hex[:6]}",
                "address_line1": "1 Test St",
                "city": "Austin", "state": "TX", "zip": "78701",
            })
            comm_id = str(comm.community_id)

            from app.models.user import User
            admin_obj = _db.session.get(User, uid_admin)
            member_obj = _db.session.get(User, uid_member)
            # Both sender and recipient must be active community members
            CommunityService.join_community(comm_id, admin_obj)
            CommunityService.join_community(comm_id, member_obj)

            ws_admin = _connect(app, tok_admin)
            ws_member = _connect(app, tok_member)

            ws_admin.emit(
                "group",
                {"type": "text", "group_id": comm_id, "body": "Group announcement"},
                namespace="/ws/messaging",
            )

            events = ws_member.get_received("/ws/messaging")
            message_events = [e for e in events if e["name"] == "message"]
            assert message_events, \
                f"Community member did not receive group 'message'; got: {events}"

            ws_admin.disconnect("/ws/messaging")
            ws_member.disconnect("/ws/messaging")


# ---------------------------------------------------------------------------
# Receipt acknowledgement (on_receipt)
# ---------------------------------------------------------------------------

class TestWsReceipt:

    def test_receipt_delivered_via_ws(self, app):
        """Sending 'receipt' with status='delivered' advances the MessageReceipt in DB."""
        uid_a, tok_a = _new_user(app)
        uid_b, tok_b = _new_user(app)

        with app.app_context():
            ws_a = _connect(app, tok_a)
            ws_b = _connect(app, tok_b)

            ws_a.emit(
                "direct",
                {"type": "text", "recipient_id": uid_b, "body": "Receipt test"},
                namespace="/ws/messaging",
            )

            receipt = MessageReceipt.query.filter_by(recipient_id=uid_b).order_by(
                MessageReceipt.updated_at.desc()
            ).first()
            assert receipt is not None
            msg_id = str(receipt.message_id)
            rid = receipt.receipt_id

            ws_b.emit(
                "receipt",
                {"message_id": msg_id, "status": "delivered"},
                namespace="/ws/messaging",
            )

            _db.session.expire(receipt)
            updated = _db.session.get(MessageReceipt, rid)
            assert updated.status == "delivered"

            ws_a.disconnect("/ws/messaging")
            ws_b.disconnect("/ws/messaging")

    def test_receipt_read_via_ws(self, app):
        """Sending 'receipt' with status='read' after 'delivered' advances to read."""
        uid_a, tok_a = _new_user(app)
        uid_b, tok_b = _new_user(app)

        with app.app_context():
            ws_a = _connect(app, tok_a)
            ws_b = _connect(app, tok_b)

            ws_a.emit(
                "direct",
                {"type": "text", "recipient_id": uid_b, "body": "Read test"},
                namespace="/ws/messaging",
            )

            receipt = MessageReceipt.query.filter_by(recipient_id=uid_b).order_by(
                MessageReceipt.updated_at.desc()
            ).first()
            msg_id = str(receipt.message_id)
            rid = receipt.receipt_id

            ws_b.emit("receipt", {"message_id": msg_id, "status": "delivered"}, namespace="/ws/messaging")
            ws_b.emit("receipt", {"message_id": msg_id, "status": "read"}, namespace="/ws/messaging")

            _db.session.expire(receipt)
            updated = _db.session.get(MessageReceipt, rid)
            assert updated.status == "read"

            ws_a.disconnect("/ws/messaging")
            ws_b.disconnect("/ws/messaging")


# ---------------------------------------------------------------------------
# Token expiry mid-connection (RISK-003)
# ---------------------------------------------------------------------------

class TestWsTokenExpiry:

    def test_expired_token_disconnects_on_next_event(self, app):
        """A connection whose session has expired is disconnected on the next event."""
        uid_a, tok_a = _new_user(app)
        uid_b, tok_b = _new_user(app)

        with app.app_context():
            ws_a = _connect(app, tok_a)
            assert ws_a.is_connected("/ws/messaging")

            # Artificially expire the session in DB
            h = hashlib.sha256(tok_a.encode()).hexdigest()
            session = _db.session.get(Session, h)
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            _db.session.commit()

            # Next event should trigger re-validation, find expired session, disconnect
            ws_a.emit(
                "direct",
                {"type": "text", "recipient_id": uid_b, "body": "Should be rejected"},
                namespace="/ws/messaging",
            )

            assert not ws_a.is_connected("/ws/messaging")
