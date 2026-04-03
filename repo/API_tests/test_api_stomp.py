"""
API functional tests for the STOMP WebSocket endpoint (/ws/stomp).

Uses _FakeWs (a mock WebSocket) to exercise _handle_stomp_connection directly.
Tests cover:
  - CONNECT with valid/invalid/empty token
  - SUBSCRIBE with receipt and authorization checks
  - SEND /app/direct with real two-client recipient routing
  - SEND /app/group with community membership validation
  - SEND /app/receipt advancing status in DB
  - DISCONNECT with receipt
  - SEND before CONNECT rejected
  - Redelivery reaching STOMP-connected recipients
  - Unauthorized community subscription rejected
"""
import json
import uuid
import threading

import pytest

from app.stomp_ws import (
    _parse_frame, _build_frame, _handle_stomp_connection,
    stomp_registry,
)
from app.services.auth_service import AuthService
from app.services.community_service import CommunityService


_NUL = "\x00"


# ---------------------------------------------------------------------------
# Fake WebSocket for in-process testing
# ---------------------------------------------------------------------------

class _FakeWs:
    """
    Minimal WebSocket stub consumed by _handle_stomp_connection.

    Frames are placed into _in before starting the handler.  The handler
    calls receive() to consume them and send() to produce replies.
    """
    def __init__(self, frames=None):
        self._in = list(frames or [])
        self._in_lock = threading.Lock()
        self._in_event = threading.Event()
        self.sent: list[str] = []
        self._sent_lock = threading.Lock()
        if self._in:
            self._in_event.set()

    def receive(self, timeout=None):
        # First check if there are frames immediately available
        with self._in_lock:
            if self._in:
                return self._in.pop(0)
        # Wait for new frames (with timeout to prevent deadlock)
        if not self._in_event.wait(timeout=timeout or 2):
            return None
        with self._in_lock:
            if self._in:
                frame = self._in.pop(0)
                if not self._in:
                    self._in_event.clear()
                return frame
        return None

    def send(self, data):
        with self._sent_lock:
            self.sent.append(data)

    def inject(self, frame):
        """Push a new frame for the handler to process (thread-safe)."""
        with self._in_lock:
            self._in.append(frame)
            self._in_event.set()

    def _parsed_sent(self):
        with self._sent_lock:
            return [_parse_frame(f) for f in list(self.sent)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(app, role="Member"):
    suffix = uuid.uuid4().hex[:8]
    username = f"stomp_{suffix}"
    with app.app_context():
        AuthService.register(username, "StompTest12!", role=role)
        result = AuthService.login(username, "StompTest12!")
    return result["user_id"], result["token"]


def _connect_frame(token):
    return _build_frame("CONNECT", {
        "accept-version": "1.2",
        "Authorization": f"Bearer {token}",
        "host": "localhost",
    })


def _subscribe_frame(destination, sub_id="sub-0", receipt=None):
    hdrs = {"id": sub_id, "destination": destination, "ack": "auto"}
    if receipt:
        hdrs["receipt"] = receipt
    return _build_frame("SUBSCRIBE", hdrs)


def _send_frame(destination, body_dict, receipt=None):
    hdrs = {"destination": destination, "content-type": "application/json"}
    if receipt:
        hdrs["receipt"] = receipt
    return _build_frame("SEND", hdrs, json.dumps(body_dict))


def _disconnect_frame(receipt="r-disc"):
    return _build_frame("DISCONNECT", {"receipt": receipt})


def _run_handler(ws, app):
    """Run _handle_stomp_connection in a background thread. Returns the thread."""
    t = threading.Thread(target=_handle_stomp_connection, args=(ws, app), daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Frame parsing / building unit tests
# ---------------------------------------------------------------------------

def test_parse_frame_connect():
    raw = "CONNECT\naccept-version:1.2\nAuthorization:Bearer tok\n\n\x00"
    cmd, hdrs, body = _parse_frame(raw)
    assert cmd == "CONNECT"
    assert hdrs["Authorization"] == "Bearer tok"
    assert body == ""


def test_build_frame_connected():
    frame = _build_frame("CONNECTED", {"version": "1.2"}, "")
    assert frame.startswith("CONNECTED\n")
    assert "version:1.2" in frame
    assert frame.endswith(_NUL)


# ---------------------------------------------------------------------------
# Connection / authentication
# ---------------------------------------------------------------------------

class TestStompConnect:

    def test_connect_valid_token(self, app):
        _, tok = _make_user(app)
        ws = _FakeWs([_connect_frame(tok)])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        cmds = [f[0] for f in ws._parsed_sent()]
        assert "CONNECTED" in cmds

    def test_connect_invalid_token(self, app):
        ws = _FakeWs([_connect_frame("notarealtoken")])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        cmds = [f[0] for f in ws._parsed_sent()]
        assert "ERROR" in cmds
        assert "CONNECTED" not in cmds

    def test_connect_empty_token(self, app):
        frame = _build_frame("CONNECT", {"accept-version": "1.2", "host": "localhost"})
        ws = _FakeWs([frame])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        cmds = [f[0] for f in ws._parsed_sent()]
        assert "ERROR" in cmds

    def test_disconnect_sends_receipt(self, app):
        _, tok = _make_user(app)
        ws = _FakeWs([_connect_frame(tok), _disconnect_frame(receipt="r-99")])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        parsed = ws._parsed_sent()
        receipt_cmds = [f for f in parsed if f[0] == "RECEIPT"]
        assert receipt_cmds
        assert any(f[1].get("receipt-id") == "r-99" for f in receipt_cmds)


# ---------------------------------------------------------------------------
# SUBSCRIBE
# ---------------------------------------------------------------------------

class TestStompSubscribe:

    def test_subscribe_sends_receipt(self, app):
        _, tok = _make_user(app)
        ws = _FakeWs([
            _connect_frame(tok),
            _subscribe_frame("/user/queue/messages", receipt="r-sub-1"),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        parsed = ws._parsed_sent()
        receipt_ids = [f[1].get("receipt-id") for f in parsed if f[0] == "RECEIPT"]
        assert "r-sub-1" in receipt_ids

    def test_subscribe_community_non_member_error(self, app):
        """Subscribe to /topic/community.X without membership -> ERROR."""
        uid_a, tok_a = _make_user(app, role="Administrator")
        with app.app_context():
            comm = CommunityService.create({
                "name": f"SubTest {uuid.uuid4().hex[:6]}",
                "address_line1": "1 St", "city": "A", "state": "TX", "zip": "78701",
            })
            comm_id = str(comm.community_id)

        # Do NOT join the community - subscription should be rejected
        ws = _FakeWs([
            _connect_frame(tok_a),
            _subscribe_frame(f"/topic/community.{comm_id}", receipt="r-bad"),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        parsed = ws._parsed_sent()
        err_frames = [f for f in parsed if f[0] == "ERROR"]
        assert err_frames, f"Expected ERROR for non-member subscribe, got: {[f[0] for f in parsed]}"
        assert "Forbidden" in err_frames[0][1].get("message", "")


# ---------------------------------------------------------------------------
# SEND /app/direct — two independent clients
# ---------------------------------------------------------------------------

class TestStompSendDirect:

    def test_send_direct_returns_message_frame(self, app):
        uid_a, tok_a = _make_user(app)
        uid_b, _ = _make_user(app)
        ws = _FakeWs([
            _connect_frame(tok_a),
            _send_frame("/app/direct", {
                "type": "text", "recipient_id": uid_b, "body": "Hello via STOMP",
            }, receipt="r-dir"),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        parsed = ws._parsed_sent()
        msg_frames = [f for f in parsed if f[0] == "MESSAGE"]
        assert msg_frames
        payload = json.loads(msg_frames[0][2])
        assert payload["body"] == "Hello via STOMP"
        assert payload["sender_id"] == uid_a

    def test_direct_recipient_receives_via_stomp(self, app):
        """User A sends direct -> User B receives on their STOMP connection.
        Uses explicit registry pre-registration for deterministic timing."""
        uid_a, tok_a = _make_user(app)
        uid_b, tok_b = _make_user(app)

        # Pre-register user B's fake ws in the stomp_registry
        ws_b = _FakeWs()
        stomp_registry.register(ws_b, uid_b)

        try:
            # User A sends a direct message
            ws_a = _FakeWs([
                _connect_frame(tok_a),
                _send_frame("/app/direct", {
                    "type": "text", "recipient_id": uid_b, "body": "cross-client direct",
                }),
                _disconnect_frame(),
            ])
            with app.app_context():
                _handle_stomp_connection(ws_a, app)

            # Verify B received a MESSAGE frame pushed via the registry
            b_parsed = ws_b._parsed_sent()
            b_messages = [f for f in b_parsed if f[0] == "MESSAGE"]
            assert b_messages, f"User B did not receive MESSAGE frame; got: {[f[0] for f in b_parsed]}"
            payload = json.loads(b_messages[0][2])
            assert payload["body"] == "cross-client direct"
            assert payload["sender_id"] == uid_a
        finally:
            stomp_registry.unregister(ws_b)

    def test_send_direct_persists_to_db(self, app):
        from app.models.messaging import MessageReceipt
        uid_a, tok_a = _make_user(app)
        uid_b, _ = _make_user(app)
        ws = _FakeWs([
            _connect_frame(tok_a),
            _send_frame("/app/direct", {
                "type": "text", "recipient_id": uid_b, "body": "Persist STOMP check",
            }),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws, app)
            from app.extensions import db
            receipts = db.session.query(MessageReceipt).filter_by(recipient_id=uid_b).all()
        assert len(receipts) >= 1


# ---------------------------------------------------------------------------
# SEND /app/group — community members only
# ---------------------------------------------------------------------------

class TestStompSendGroup:

    def test_send_group_delivered_to_subscribers(self, app):
        """Group message reaches only subscribed community members.
        Uses explicit registry pre-registration for deterministic timing."""
        uid_admin, tok_admin = _make_user(app, role="Administrator")
        uid_member, _ = _make_user(app)

        with app.app_context():
            comm = CommunityService.create({
                "name": f"StompComm {uuid.uuid4().hex[:6]}",
                "address_line1": "1 STOMP St",
                "city": "Austin", "state": "TX", "zip": "78701",
            })
            comm_id = str(comm.community_id)
            from app.extensions import db
            from app.models.user import User
            admin_obj = db.session.get(User, uid_admin)
            member_obj = db.session.get(User, uid_member)
            CommunityService.join_community(comm_id, admin_obj)
            CommunityService.join_community(comm_id, member_obj)

        # Pre-register member's fake ws and subscribe to community topic
        ws_member = _FakeWs()
        stomp_registry.register(ws_member, uid_member)
        stomp_registry.subscribe(ws_member, "s1", f"/topic/community.{comm_id}")

        try:
            # Admin sends a group message
            ws_admin = _FakeWs([
                _connect_frame(tok_admin),
                _send_frame("/app/group", {
                    "type": "text", "group_id": comm_id, "body": "Group STOMP msg",
                }),
                _disconnect_frame(),
            ])
            with app.app_context():
                _handle_stomp_connection(ws_admin, app)

            member_parsed = ws_member._parsed_sent()
            member_msgs = [f for f in member_parsed if f[0] == "MESSAGE"]
            assert member_msgs, f"Member did not receive group MESSAGE; got: {[f[0] for f in member_parsed]}"
            payload = json.loads(member_msgs[0][2])
            assert payload["body"] == "Group STOMP msg"
        finally:
            stomp_registry.unregister(ws_member)

    def test_send_group_non_member_forbidden(self, app):
        """Sending a group message without community membership -> ERROR."""
        uid_a, tok_a = _make_user(app, role="Administrator")
        with app.app_context():
            comm = CommunityService.create({
                "name": f"NoJoin {uuid.uuid4().hex[:6]}",
                "address_line1": "1 St", "city": "A", "state": "TX", "zip": "78701",
            })
            comm_id = str(comm.community_id)
        # Do NOT join
        ws = _FakeWs([
            _connect_frame(tok_a),
            _send_frame("/app/group", {
                "type": "text", "group_id": comm_id, "body": "Should fail",
            }),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        parsed = ws._parsed_sent()
        err_frames = [f for f in parsed if f[0] == "ERROR"]
        assert err_frames, f"Expected ERROR for non-member group send, got: {[f[0] for f in parsed]}"


# ---------------------------------------------------------------------------
# SEND /app/receipt
# ---------------------------------------------------------------------------

class TestStompReceipt:

    def test_send_receipt_advances_status(self, app):
        from app.models.messaging import MessageReceipt
        uid_a, tok_a = _make_user(app)
        uid_b, tok_b = _make_user(app)

        ws_send = _FakeWs([
            _connect_frame(tok_a),
            _send_frame("/app/direct", {"type": "text", "recipient_id": uid_b, "body": "receipt test"}),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws_send, app)
            from app.extensions import db
            receipt = db.session.query(MessageReceipt).filter_by(
                recipient_id=uid_b,
            ).order_by(MessageReceipt.updated_at.desc()).first()
            assert receipt is not None
            msg_id = str(receipt.message_id)
            rid = receipt.receipt_id

        ws_ack = _FakeWs([
            _connect_frame(tok_b),
            _send_frame("/app/receipt", {"message_id": msg_id, "status": "delivered"}),
            _disconnect_frame(),
        ])
        with app.app_context():
            _handle_stomp_connection(ws_ack, app)
            from app.extensions import db
            updated = db.session.get(MessageReceipt, rid)
            assert updated.status == "delivered"


# ---------------------------------------------------------------------------
# Redelivery path reaches STOMP client
# ---------------------------------------------------------------------------

class TestStompRedelivery:

    def test_redelivery_pushes_to_stomp_client(self, app):
        """When a recipient is online via STOMP, the redelivery job pushes
        the message frame to their connection."""
        uid_a, tok_a = _make_user(app)
        uid_b, _ = _make_user(app)

        # Create a message with a sent receipt for user B
        with app.app_context():
            from app.services.messaging_service import MessagingService
            from app.extensions import db
            from app.models.user import User
            sender = db.session.get(User, uid_a)
            MessagingService.send_message(
                {"type": "text", "recipient_id": uid_b, "body": "redeliver me"},
                sender=sender,
            )

        # Pre-register user B in stomp_registry
        ws_b = _FakeWs()
        stomp_registry.register(ws_b, uid_b)

        try:
            # Run redelivery job
            with app.app_context():
                from app.jobs.message_redelivery import redeliver_messages
                redeliver_messages()

            b_parsed = ws_b._parsed_sent()
            b_msgs = [f for f in b_parsed if f[0] == "MESSAGE"]
            assert b_msgs, f"Redelivery did not push MESSAGE to STOMP client; got: {[f[0] for f in b_parsed]}"
            payload = json.loads(b_msgs[0][2])
            assert payload["body"] == "redeliver me"
        finally:
            stomp_registry.unregister(ws_b)


# ---------------------------------------------------------------------------
# SEND before CONNECT
# ---------------------------------------------------------------------------

class TestStompNoAuth:

    def test_send_without_connect_returns_error(self, app):
        uid_b, _ = _make_user(app)
        ws = _FakeWs([
            _send_frame("/app/direct", {"type": "text", "recipient_id": uid_b, "body": "nope"}),
        ])
        with app.app_context():
            _handle_stomp_connection(ws, app)
        cmds = [f[0] for f in ws._parsed_sent()]
        assert "ERROR" in cmds
