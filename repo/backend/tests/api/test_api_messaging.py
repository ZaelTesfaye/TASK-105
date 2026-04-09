"""
API functional tests for messaging REST endpoints.

Covers: send direct/group messages, message queuing, delivery/read receipts,
        status regression enforcement, invalid inputs, and auth requirements.
All tests use the Flask test client against /api/v1/messages/* endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, role="Member"):
    username = f"user_{uuid.uuid4().hex[:8]}"
    password = "ValidPass1234!"
    reg = client.post(f"{BASE}/auth/register", json={
        "username": username,
        "password": password,
        "role": role,
    })
    user_id = reg.json["user_id"]
    token = client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    }).json["token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def _send_direct(client, sender_headers, recipient_id, body="Hello!"):
    return client.post(f"{BASE}/messages", json={
        "type": "text",
        "recipient_id": recipient_id,
        "body": body,
    }, headers=sender_headers)


def _create_community(client, headers):
    resp = client.post(f"{BASE}/communities", json={
        "name": f"Comm_{uuid.uuid4().hex[:6]}",
        "address_line1": "1 Main St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["community_id"]


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------

def test_send_direct_201(client, auth_headers):
    """POST /messages with type/recipient_id/body returns 201 with expected fields."""
    recip_id, _ = _register_and_login(client)
    resp = _send_direct(client, auth_headers, recip_id)
    assert resp.status_code == 201
    data = resp.json
    assert "message_id" in data
    assert "sender_id" in data
    assert "recipient_id" in data
    assert "sent_at" in data
    assert data["recipient_id"] == recip_id


def test_send_requires_auth_401(client):
    """POST /messages without a token returns 401."""
    resp = client.post(f"{BASE}/messages", json={
        "type": "text",
        "body": "no auth",
    })
    assert resp.status_code == 401


def test_send_invalid_type_400(client, auth_headers):
    """POST /messages with type=voice returns 400 with error=invalid_message_type."""
    recip_id, _ = _register_and_login(client)
    resp = client.post(f"{BASE}/messages", json={
        "type": "voice",
        "recipient_id": recip_id,
        "body": "hi",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_message_type"


def test_send_both_targets_400(client, auth_headers):
    """Providing both recipient_id and group_id returns 400 with error=ambiguous_target."""
    recip_id, _ = _register_and_login(client)
    group_id = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/messages", json={
        "type": "text",
        "recipient_id": recip_id,
        "group_id": group_id,
        "body": "ambiguous",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "ambiguous_target"


# ---------------------------------------------------------------------------
# Queue polling
# ---------------------------------------------------------------------------

def test_get_queued_200(client, auth_headers):
    """Recipient GET /messages returns 200 and the array contains the sent message."""
    recip_id, recip_headers = _register_and_login(client)
    _send_direct(client, auth_headers, recip_id, body="queue_test_body")
    resp = client.get(f"{BASE}/messages", headers=recip_headers)
    assert resp.status_code == 200
    msgs = resp.json
    assert isinstance(msgs, list)
    assert any(m["body"] == "queue_test_body" for m in msgs)


def test_sender_queue_empty(client, auth_headers):
    """Sender GET /messages does not see the messages they sent (no receipt for sender)."""
    recip_id, _ = _register_and_login(client)
    _send_direct(client, auth_headers, recip_id, body="sender_check_body")
    resp = client.get(f"{BASE}/messages", headers=auth_headers)
    assert resp.status_code == 200
    assert not any(m.get("body") == "sender_check_body" for m in resp.json)


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------

def test_receipt_delivered_200(client, auth_headers):
    """POST /messages/{id}/receipt with status=delivered returns 200."""
    recip_id, recip_headers = _register_and_login(client)
    msg_id = _send_direct(client, auth_headers, recip_id).json["message_id"]
    resp = client.post(f"{BASE}/messages/{msg_id}/receipt",
                       json={"status": "delivered"}, headers=recip_headers)
    assert resp.status_code == 200


def test_receipt_read_200(client, auth_headers):
    """POST /messages/{id}/receipt with status=read returns 200."""
    recip_id, recip_headers = _register_and_login(client)
    msg_id = _send_direct(client, auth_headers, recip_id).json["message_id"]
    client.post(f"{BASE}/messages/{msg_id}/receipt",
                json={"status": "delivered"}, headers=recip_headers)
    resp = client.post(f"{BASE}/messages/{msg_id}/receipt",
                       json={"status": "read"}, headers=recip_headers)
    assert resp.status_code == 200


def test_receipt_backward_409(client, auth_headers):
    """Marking a message delivered, then delivered again (regression) returns 409 with error=status_regression."""
    recip_id, recip_headers = _register_and_login(client)
    msg_id = _send_direct(client, auth_headers, recip_id).json["message_id"]
    # Advance to read
    client.post(f"{BASE}/messages/{msg_id}/receipt",
                json={"status": "read"}, headers=recip_headers)
    # Try to go back to delivered (regression)
    resp = client.post(f"{BASE}/messages/{msg_id}/receipt",
                       json={"status": "delivered"}, headers=recip_headers)
    assert resp.status_code == 409
    assert resp.json["error"] == "status_regression"


def test_receipt_invalid_status_400(client, auth_headers):
    """POST /messages/{id}/receipt with status=pending returns 400."""
    recip_id, recip_headers = _register_and_login(client)
    msg_id = _send_direct(client, auth_headers, recip_id).json["message_id"]
    resp = client.post(f"{BASE}/messages/{msg_id}/receipt",
                       json={"status": "pending"}, headers=recip_headers)
    assert resp.status_code == 400


def test_receipt_not_found_404(client, auth_headers):
    """POST /messages/{random_id}/receipt returns 404."""
    resp = client.post(f"{BASE}/messages/{uuid.uuid4()}/receipt",
                       json={"status": "delivered"}, headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Group messages
# ---------------------------------------------------------------------------

def test_group_message_201(client, auth_headers, member_headers):
    """POST /messages with group_id after joining community returns 201."""
    community_id = _create_community(client, auth_headers)
    # Both sender (admin) and member must join; sender membership is enforced
    client.post(f"{BASE}/communities/{community_id}/members", headers=auth_headers)
    client.post(f"{BASE}/communities/{community_id}/members", headers=member_headers)
    resp = client.post(f"{BASE}/messages", json={
        "type": "text",
        "group_id": community_id,
        "body": "Group hello",
    }, headers=auth_headers)
    assert resp.status_code == 201


def test_group_message_non_member_403(client, auth_headers):
    """Sending a group message without being a community member returns 403."""
    community_id = _create_community(client, auth_headers)
    # Sender does NOT join the community
    resp = client.post(f"{BASE}/messages", json={
        "type": "text",
        "group_id": community_id,
        "body": "Non-member attempt",
    }, headers=auth_headers)
    assert resp.status_code == 403
