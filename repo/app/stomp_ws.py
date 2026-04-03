"""
STOMP 1.2 WebSocket endpoint at /ws/stomp.

Provides a standards-compliant STOMP interface alongside the existing
Socket.IO endpoint (/ws/messaging) for backward compatibility.

Supported client frames: CONNECT, STOMP, SUBSCRIBE, UNSUBSCRIBE, SEND, DISCONNECT
Server frames sent:      CONNECTED, MESSAGE, RECEIPT, ERROR

Authentication:
  CONNECT/STOMP frame must include header:
    Authorization: Bearer <token>
  Invalid or missing token -> ERROR frame + connection closed.

Destinations (SEND):
  /app/direct   body JSON: {"type":"text","recipient_id":"<uid>","body":"..."}
  /app/group    body JSON: {"type":"text","group_id":"<community_id>","body":"..."}
  /app/receipt  body JSON: {"message_id":"<id>","status":"delivered|read"}

Read-only destinations (SUBSCRIBE -- server pushes):
  /user/queue/messages            personal messages
  /topic/community.<community_id> community group messages
"""
import hashlib
import json
import logging
import threading
import re

log = logging.getLogger(__name__)

_NUL = "\x00"


# ---------------------------------------------------------------------------
# Thread-safe connection / subscription registry
# ---------------------------------------------------------------------------

class _StompRegistry:
    """
    Tracks active STOMP connections and their subscriptions so messages
    can be pushed to the correct recipient's WebSocket.

    Thread-safe: all mutations are guarded by a Lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # user_id -> set of _ConnEntry
        self._by_user: dict[str, set] = {}
        # subscription tracking: (ws_id, sub_id) -> destination
        self._subs: dict[tuple[int, str], str] = {}
        # ws id(ws) -> _ConnEntry
        self._by_ws: dict[int, object] = {}

    def register(self, ws, user_id: str):
        entry = _ConnEntry(ws, user_id)
        ws_id = id(ws)
        with self._lock:
            self._by_user.setdefault(user_id, set()).add(entry)
            self._by_ws[ws_id] = entry

    def unregister(self, ws):
        ws_id = id(ws)
        with self._lock:
            entry = self._by_ws.pop(ws_id, None)
            if entry is None:
                return
            user_set = self._by_user.get(entry.user_id)
            if user_set:
                user_set.discard(entry)
                if not user_set:
                    del self._by_user[entry.user_id]
            # Clean up subscriptions for this ws
            to_remove = [k for k in self._subs if k[0] == ws_id]
            for k in to_remove:
                del self._subs[k]

    def subscribe(self, ws, sub_id: str, destination: str):
        with self._lock:
            self._subs[(id(ws), sub_id)] = destination

    def unsubscribe(self, ws, sub_id: str):
        with self._lock:
            self._subs.pop((id(ws), sub_id), None)

    def get_subscribed_destinations(self, ws) -> set[str]:
        ws_id = id(ws)
        with self._lock:
            return {dest for (wid, _), dest in self._subs.items() if wid == ws_id}

    def push_to_user(self, user_id: str, frame: str) -> int:
        """Send *frame* to all STOMP connections for *user_id*.
        Returns number of connections that received the frame."""
        with self._lock:
            entries = list(self._by_user.get(user_id, []))
        sent = 0
        for entry in entries:
            try:
                entry.ws.send(frame)
                sent += 1
            except Exception:
                log.debug("push_to_user failed for user %s", user_id)
        return sent

    def push_to_community(self, community_id: str, frame: str) -> int:
        """Send *frame* to all users subscribed to /topic/community.<community_id>."""
        dest = f"/topic/community.{community_id}"
        with self._lock:
            target_ws_ids = {wid for (wid, _), d in self._subs.items() if d == dest}
            entries = [self._by_ws[wid] for wid in target_ws_ids if wid in self._by_ws]
        sent = 0
        for entry in entries:
            try:
                entry.ws.send(frame)
                sent += 1
            except Exception:
                pass
        return sent

    def is_user_online(self, user_id: str) -> bool:
        with self._lock:
            return bool(self._by_user.get(user_id))


class _ConnEntry:
    __slots__ = ("ws", "user_id")

    def __init__(self, ws, user_id: str):
        self.ws = ws
        self.user_id = user_id

    def __hash__(self):
        return id(self.ws)

    def __eq__(self, other):
        return isinstance(other, _ConnEntry) and id(self.ws) == id(other.ws)


# Module-level singleton registry
stomp_registry = _StompRegistry()


# ---------------------------------------------------------------------------
# Frame parsing / serialisation
# ---------------------------------------------------------------------------

def _parse_frame(raw: str) -> tuple[str, dict, str]:
    """Parse a STOMP frame string into (command, headers, body)."""
    raw = raw.lstrip("\n\r")
    if "\n\n" in raw:
        head, body = raw.split("\n\n", 1)
    else:
        head, body = raw, ""
    body = body.rstrip(_NUL)
    lines = head.split("\n")
    command = lines[0].strip()
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    return command, headers, body


def _build_frame(command: str, headers: dict | None = None, body: str = "") -> str:
    """Serialise a STOMP frame to a string."""
    parts = [command, "\n"]
    for k, v in (headers or {}).items():
        parts.append(f"{k}:{v}\n")
    parts.append("\n")
    parts.append(body)
    parts.append(_NUL)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Token -> User helper (mirrors websocket.py _load_user)
# ---------------------------------------------------------------------------

def _load_user_from_token(token: str):
    if not token:
        return None
    from datetime import datetime, timezone
    from app.extensions import db
    from app.models.user import Session, User
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.session.get(Session, token_hash)
    if session is None:
        return None
    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    user = db.session.get(User, session.user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


def _validate_community_membership(user_id: str, community_id: str) -> bool:
    """Return True if user is an active member of the community."""
    from app.models.community import CommunityMember
    return CommunityMember.query.filter_by(
        community_id=community_id, user_id=user_id, left_at=None,
    ).first() is not None


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

def _handle_stomp_connection(ws, app):
    """
    Run the STOMP session loop for a single WebSocket connection.
    Blocks until the client disconnects or an unrecoverable error occurs.
    """
    user = None
    user_id = None

    def send_error(message: str, receipt_id: str | None = None):
        hdrs = {"message": message, "content-type": "text/plain"}
        if receipt_id:
            hdrs["receipt-id"] = receipt_id
        ws.send(_build_frame("ERROR", hdrs, message))

    def send_receipt(receipt_id: str):
        ws.send(_build_frame("RECEIPT", {"receipt-id": receipt_id}))

    try:
        while True:
            try:
                raw = ws.receive(timeout=60)
            except Exception:
                break
            if raw is None:
                break

            try:
                command, headers, body = _parse_frame(raw)
            except Exception:
                send_error("Malformed STOMP frame")
                break

            command = command.upper()

            # ---- CONNECT / STOMP ----
            if command in ("CONNECT", "STOMP"):
                auth_header = headers.get("Authorization", headers.get("authorization", ""))
                token = ""
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:].strip()
                with app.app_context():
                    user = _load_user_from_token(token)
                if user is None:
                    send_error("Authentication failed -- invalid or expired token")
                    break
                user_id = str(user.user_id)
                stomp_registry.register(ws, user_id)
                ws.send(_build_frame("CONNECTED", {
                    "version": "1.2",
                    "server": "NeighborhoodCommerce/1.0",
                    "heart-beat": "0,0",
                }))

            # ---- SUBSCRIBE ----
            elif command == "SUBSCRIBE":
                if user is None:
                    send_error("Not authenticated")
                    break
                sub_id = headers.get("id", "")
                destination = headers.get("destination", "")

                # Authorisation check for community topics
                m = re.match(r"^/topic/community\.(.+)$", destination)
                if m:
                    community_id = m.group(1)
                    with app.app_context():
                        if not _validate_community_membership(user_id, community_id):
                            send_error(
                                f"Forbidden: not a member of community {community_id}",
                                headers.get("receipt"),
                            )
                            continue

                stomp_registry.subscribe(ws, sub_id, destination)
                if receipt_id := headers.get("receipt"):
                    send_receipt(receipt_id)

            # ---- UNSUBSCRIBE ----
            elif command == "UNSUBSCRIBE":
                sub_id = headers.get("id", "")
                stomp_registry.unsubscribe(ws, sub_id)
                if receipt_id := headers.get("receipt"):
                    send_receipt(receipt_id)

            # ---- SEND ----
            elif command == "SEND":
                if user is None:
                    send_error("Not authenticated")
                    break
                destination = headers.get("destination", "")
                receipt_id = headers.get("receipt")
                try:
                    payload = json.loads(body) if body.strip() else {}
                except json.JSONDecodeError:
                    send_error("Body must be valid JSON", receipt_id)
                    continue

                try:
                    with app.app_context():
                        from app.extensions import db
                        from app.models.user import User as UserModel
                        live_user = db.session.get(UserModel, user.user_id)
                        if live_user is None:
                            send_error("User not found")
                            break

                        from app.services.messaging_service import MessagingService

                        if destination == "/app/direct":
                            msg = MessagingService.send_message(payload, sender=live_user)
                            msg_dict = msg.to_dict()
                            frame = _build_frame("MESSAGE", {
                                "destination": "/user/queue/messages",
                                "content-type": "application/json",
                                "message-id": str(msg.message_id),
                            }, json.dumps(msg_dict))

                            # Deliver to sender (echo)
                            ws.send(frame)
                            # Deliver to recipient if they have active STOMP connections
                            recipient_id = payload.get("recipient_id")
                            if recipient_id and recipient_id != user_id:
                                stomp_registry.push_to_user(recipient_id, frame)

                        elif destination == "/app/group":
                            msg = MessagingService.send_message(payload, sender=live_user)
                            msg_dict = msg.to_dict()
                            group_id = payload.get("group_id", "")
                            frame = _build_frame("MESSAGE", {
                                "destination": f"/topic/community.{group_id}",
                                "content-type": "application/json",
                                "message-id": str(msg.message_id),
                            }, json.dumps(msg_dict))

                            # Deliver to all subscribed community members
                            stomp_registry.push_to_community(group_id, frame)
                            # Also echo to sender if not already subscribed
                            dests = stomp_registry.get_subscribed_destinations(ws)
                            if f"/topic/community.{group_id}" not in dests:
                                ws.send(frame)

                        elif destination == "/app/receipt":
                            MessagingService.update_receipt(
                                payload["message_id"], payload["status"], user=live_user,
                            )

                        else:
                            send_error(f"Unknown destination: {destination}", receipt_id)
                            continue

                        if receipt_id:
                            send_receipt(receipt_id)

                except Exception as exc:
                    log.exception("STOMP SEND error for destination %s", destination)
                    send_error(str(exc), receipt_id)

            # ---- DISCONNECT ----
            elif command == "DISCONNECT":
                if receipt_id := headers.get("receipt"):
                    send_receipt(receipt_id)
                break

            else:
                send_error(f"Unknown command: {command}")
                break
    finally:
        stomp_registry.unregister(ws)


# ---------------------------------------------------------------------------
# Registration helper called from app factory
# ---------------------------------------------------------------------------

def register_stomp(app):
    """Wire the STOMP WebSocket route into *app* using flask-sock."""
    try:
        from flask_sock import Sock
    except ImportError:
        log.warning("flask-sock not installed; STOMP endpoint disabled")
        return

    sock = Sock(app)

    @sock.route("/ws/stomp")
    def stomp_endpoint(ws):
        _handle_stomp_connection(ws, app)
