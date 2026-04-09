"""
Messaging REST endpoint tests.
Covers: send (direct/group), queue polling, delivery/read receipts,
        status progression enforcement, TTL, invalid inputs, auth.
"""
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, role="Member"):
    username = f"u_{uuid.uuid4().hex[:8]}"
    password = "ValidPass1234!"
    reg = client.post("/api/v1/auth/register", json={
        "username": username, "password": password, "role": role,
    })
    user_id = reg.json["user_id"]
    token = client.post("/api/v1/auth/login", json={
        "username": username, "password": password,
    }).json["token"]
    return user_id, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------

def test_send_direct_message(client, auth_headers):
    """POST /messages with recipient_id → 201 + message body."""
    recip_id, recip_headers = _register_and_login(client)

    resp = client.post("/api/v1/messages", json={
        "type": "text",
        "recipient_id": recip_id,
        "body": "Hello!",
    }, headers=auth_headers)
    assert resp.status_code == 201
    d = resp.json
    assert d["type"] == "text"
    assert d["body"] == "Hello!"
    assert d["recipient_id"] == recip_id
    assert "message_id" in d


def test_send_group_message(client, auth_headers):
    """POST /messages with group_id → 201 (sender must be an active community member)."""
    # Create a community first
    comm_resp = client.post("/api/v1/communities", json={
        "name": f"Grp-{uuid.uuid4().hex[:6]}",
        "address_line1": "1 A St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=auth_headers)
    assert comm_resp.status_code == 201
    group_id = comm_resp.json["community_id"]

    # Sender must join the community before sending a group message
    join_resp = client.post(f"/api/v1/communities/{group_id}/members", headers=auth_headers)
    assert join_resp.status_code == 201

    resp = client.post("/api/v1/messages", json={
        "type": "text",
        "group_id": group_id,
        "body": "Group hello",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["group_id"] == group_id


def test_send_both_targets_rejected(client, auth_headers):
    """recipient_id AND group_id together → 400."""
    recip_id, recip_headers = _register_and_login(client)
    comm_resp = client.post("/api/v1/communities", json={
        "name": f"C-{uuid.uuid4().hex[:6]}",
        "address_line1": "1 B St", "city": "Austin", "state": "TX", "zip": "78701",
    }, headers=auth_headers)
    group_id = comm_resp.json["community_id"]

    resp = client.post("/api/v1/messages", json={
        "type": "text",
        "recipient_id": recip_id,
        "group_id": group_id,
        "body": "Oops",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "ambiguous_target"


def test_send_invalid_message_type(client, auth_headers):
    """Unknown type → 400."""
    recip_id, recip_headers = _register_and_login(client)

    resp = client.post("/api/v1/messages", json={
        "type": "video",
        "recipient_id": recip_id,
        "body": "hi",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_message_type"


def test_send_requires_auth(client):
    """No auth → 401."""
    resp = client.post("/api/v1/messages", json={
        "type": "text",
        "body": "hi",
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Queue polling
# ---------------------------------------------------------------------------

def test_get_queued_messages(client, auth_headers):
    """Recipient can poll undelivered messages."""
    recip_id, recip_headers = _register_and_login(client)

    # Send a message
    client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "Queue test",
    }, headers=auth_headers)

    # Recipient polls
    resp = client.get("/api/v1/messages", headers=recip_headers)
    assert resp.status_code == 200
    msgs = resp.json
    assert isinstance(msgs, list)
    assert any(m["body"] == "Queue test" for m in msgs)


def test_sender_has_empty_queue(client, auth_headers):
    """Sender doesn't see messages they sent (no receipt for themselves)."""
    recip_id, recip_headers = _register_and_login(client)

    client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "Sender check",
    }, headers=auth_headers)

    # Sender's own queue should be empty (they have no receipt)
    resp = client.get("/api/v1/messages", headers=auth_headers)
    assert resp.status_code == 200
    # The sent message should NOT appear in sender's queue
    assert not any(m["body"] == "Sender check" for m in resp.json)


# ---------------------------------------------------------------------------
# Delivery / read receipts
# ---------------------------------------------------------------------------

def _send_to_recipient(client, sender_headers, recip_id):
    resp = client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "Receipt test",
    }, headers=sender_headers)
    assert resp.status_code == 201
    return resp.json["message_id"]


def test_receipt_delivered(client, auth_headers):
    """Recipient can mark a message as delivered."""
    recip_id, recip_headers = _register_and_login(client)
    mid = _send_to_recipient(client, auth_headers, recip_id)

    resp = client.post(f"/api/v1/messages/{mid}/receipt",
                       json={"status": "delivered"}, headers=recip_headers)
    assert resp.status_code == 200
    assert resp.json["delivery_status"] == "delivered"


def test_receipt_read(client, auth_headers):
    """Recipient can advance status to read."""
    recip_id, recip_headers = _register_and_login(client)
    mid = _send_to_recipient(client, auth_headers, recip_id)

    # delivered first
    client.post(f"/api/v1/messages/{mid}/receipt",
                json={"status": "delivered"}, headers=recip_headers)
    # then read
    resp = client.post(f"/api/v1/messages/{mid}/receipt",
                       json={"status": "read"}, headers=recip_headers)
    assert resp.status_code == 200
    assert resp.json["delivery_status"] == "read"


def test_receipt_backward_transition_blocked(client, auth_headers):
    """read → delivered must be rejected (409)."""
    recip_id, recip_headers = _register_and_login(client)
    mid = _send_to_recipient(client, auth_headers, recip_id)

    # advance to read
    client.post(f"/api/v1/messages/{mid}/receipt",
                json={"status": "read"}, headers=recip_headers)
    # try to go back
    resp = client.post(f"/api/v1/messages/{mid}/receipt",
                       json={"status": "delivered"}, headers=recip_headers)
    assert resp.status_code == 409
    assert resp.json["error"] == "status_regression"


def test_receipt_sent_to_delivered_skip_ok(client, auth_headers):
    """sent → read (skip delivered) is allowed — just a forward jump."""
    recip_id, recip_headers = _register_and_login(client)
    mid = _send_to_recipient(client, auth_headers, recip_id)

    resp = client.post(f"/api/v1/messages/{mid}/receipt",
                       json={"status": "read"}, headers=recip_headers)
    assert resp.status_code == 200
    assert resp.json["delivery_status"] == "read"


def test_receipt_invalid_status(client, auth_headers):
    """status='sent' is not a valid target transition value."""
    recip_id, recip_headers = _register_and_login(client)
    mid = _send_to_recipient(client, auth_headers, recip_id)

    resp = client.post(f"/api/v1/messages/{mid}/receipt",
                       json={"status": "sent"}, headers=recip_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_status"


def test_receipt_not_found(client, auth_headers):
    """Receipt for a message the user didn't receive → 404."""
    resp = client.post(f"/api/v1/messages/{uuid.uuid4()}/receipt",
                       json={"status": "delivered"}, headers=auth_headers)
    assert resp.status_code == 404


def test_queue_cleared_after_delivered(client, auth_headers):
    """Messages marked 'delivered' no longer appear in the 'sent' queue."""
    recip_id, recip_headers = _register_and_login(client)
    mid = _send_to_recipient(client, auth_headers, recip_id)

    # Confirm message is in queue
    queue_before = client.get("/api/v1/messages", headers=recip_headers).json
    assert any(m["message_id"] == mid for m in queue_before)

    # Mark delivered
    client.post(f"/api/v1/messages/{mid}/receipt",
                json={"status": "delivered"}, headers=recip_headers)

    # Should not appear in 'sent' queue anymore
    queue_after = client.get("/api/v1/messages", headers=recip_headers).json
    assert not any(m["message_id"] == mid for m in queue_after)
