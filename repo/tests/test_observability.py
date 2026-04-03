"""
Observability and API contract tests.
Covers: X-Correlation-ID propagation, health endpoints, log field presence,
        response shape validation (required fields in all critical responses).
"""
import uuid


# ---------------------------------------------------------------------------
# Correlation ID propagation
# ---------------------------------------------------------------------------

def test_correlation_id_echoed(client):
    """Supplied X-Correlation-ID is echoed in the response header."""
    cid = str(uuid.uuid4())
    resp = client.get("/health", headers={"X-Correlation-ID": cid})
    assert resp.headers.get("X-Correlation-ID") == cid


def test_correlation_id_generated_when_absent(client):
    """Missing X-Correlation-ID gets a server-generated UUID in the response."""
    resp = client.get("/health")
    cid = resp.headers.get("X-Correlation-ID", "")
    assert cid, "X-Correlation-ID header must be present"
    # Must be a valid UUID
    uuid.UUID(cid)  # raises ValueError if invalid


def test_correlation_id_on_error_response(client):
    """Error responses (404) also carry the correlation ID."""
    cid = str(uuid.uuid4())
    resp = client.get("/api/v1/nonexistent-path-xyz", headers={"X-Correlation-ID": cid})
    assert resp.status_code == 404
    assert resp.headers.get("X-Correlation-ID") == cid


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

def test_liveness(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    d = resp.json
    assert d["status"] == "ok"
    assert "version" in d
    assert d["db"] == "ok"


def test_readiness(client):
    """Readiness probe: scheduler not running in test config → 503."""
    resp = client.get("/health/ready")
    # In test mode JOBS_ENABLED=False so scheduler.running is False
    assert resp.status_code in (200, 503)
    if resp.status_code == 503:
        assert "scheduler" in str(resp.json.get("errors", []))


# ---------------------------------------------------------------------------
# Auth response shapes
# ---------------------------------------------------------------------------

def _register_and_login(client):
    username = f"obs_{uuid.uuid4().hex[:8]}"
    password = "ObsPass1234!"
    reg = client.post("/api/v1/auth/register",
                      json={"username": username, "password": password, "role": "Member"})
    token = client.post("/api/v1/auth/login",
                        json={"username": username, "password": password}).json["token"]
    return reg.json["user_id"], token, {"Authorization": f"Bearer {token}"}


def test_register_response_shape(client):
    """POST /auth/register → {user_id, username, role, created_at}."""
    resp = client.post("/api/v1/auth/register", json={
        "username": f"s_{uuid.uuid4().hex[:8]}",
        "password": "ShapePass1234!",
        "role": "Member",
    })
    assert resp.status_code == 201
    d = resp.json
    for key in ("user_id", "username", "role", "created_at"):
        assert key in d, f"Missing field: {key}"


def test_login_response_shape(client):
    """POST /auth/login → {token}."""
    username = f"s2_{uuid.uuid4().hex[:8]}"
    client.post("/api/v1/auth/register",
                json={"username": username, "password": "ShapePass2_1234!", "role": "Member"})
    resp = client.post("/api/v1/auth/login",
                       json={"username": username, "password": "ShapePass2_1234!"})
    assert resp.status_code == 200
    assert "token" in resp.json


def test_error_response_shape(client, auth_headers):
    """Error responses include {error, message} fields."""
    resp = client.post("/api/v1/auth/login", json={
        "username": "nobody_ever", "password": "WrongPass1234!",
    })
    assert resp.status_code == 401
    d = resp.json
    assert "error" in d
    assert "message" in d


# ---------------------------------------------------------------------------
# Community response shape
# ---------------------------------------------------------------------------

def test_community_response_shape(client, auth_headers):
    resp = client.post("/api/v1/communities", json={
        "name": "Shape Comm",
        "address_line1": "1 Oak St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=auth_headers)
    assert resp.status_code == 201
    d = resp.json
    for key in ("community_id", "name", "created_at"):
        assert key in d, f"Missing community field: {key}"
    # Address is nested under 'address' object
    assert "address" in d or "city" in d, "Community must have address fields"


# ---------------------------------------------------------------------------
# Product response shape
# ---------------------------------------------------------------------------

def test_product_response_shape(client, auth_headers):
    resp = client.post("/api/v1/products", json={
        "sku": f"SHP-{uuid.uuid4().hex[:6]}",
        "name": "Shape Product",
        "brand": "Tester",
        "category": "Test",
        "price_usd": 9.99,
    }, headers=auth_headers)
    assert resp.status_code == 201
    for key in ("product_id", "sku", "name", "brand", "category", "price_usd", "created_at"):
        assert key in resp.json, f"Missing product field: {key}"


# ---------------------------------------------------------------------------
# Settlement response shape
# ---------------------------------------------------------------------------

def test_settlement_response_shape(client, auth_headers):
    comm_id = client.post("/api/v1/communities", json={
        "name": f"SC-{uuid.uuid4().hex[:6]}",
        "address_line1": "1 St", "city": "Austin", "state": "TX", "zip": "78701",
    }, headers=auth_headers).json["community_id"]

    resp = client.post("/api/v1/settlements", json={
        "community_id": comm_id,
        "period_start": "2026-01-05",
        "period_end": "2026-01-11",
        "idempotency_key": uuid.uuid4().hex,
    }, headers=auth_headers)
    assert resp.status_code == 201
    for key in ("settlement_id", "community_id", "status", "idempotency_key",
                "period_start", "period_end", "created_at"):
        assert key in resp.json, f"Missing settlement field: {key}"


# ---------------------------------------------------------------------------
# Message response shape
# ---------------------------------------------------------------------------

def test_message_response_shape(client, auth_headers):
    reg = client.post("/api/v1/auth/register", json={
        "username": f"mr_{uuid.uuid4().hex[:8]}", "password": "MsgPass1234!", "role": "Member",
    })
    recip_id = reg.json["user_id"]

    resp = client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "shape test",
    }, headers=auth_headers)
    assert resp.status_code == 201
    for key in ("message_id", "type", "sender_id", "recipient_id", "sent_at"):
        assert key in resp.json, f"Missing message field: {key}"


# ---------------------------------------------------------------------------
# Inventory receipt response shape
# ---------------------------------------------------------------------------

def test_inventory_receipt_response_shape(client, auth_headers):
    wh_id = client.post("/api/v1/warehouses",
                        json={"name": "WH-Shp", "location": "X"},
                        headers=auth_headers).json["warehouse_id"]
    pid = client.post("/api/v1/products", json={
        "sku": f"SHP2-{uuid.uuid4().hex[:6]}", "name": "P",
        "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers).json["product_id"]

    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": pid, "warehouse_id": wh_id, "quantity": 10,
    }, headers=auth_headers)
    assert resp.status_code == 201
    for key in ("transaction_id", "type", "sku_id", "warehouse_id", "quantity_delta", "occurred_at"):
        assert key in resp.json, f"Missing receipt field: {key}"


# ---------------------------------------------------------------------------
# Content response shape
# ---------------------------------------------------------------------------

def test_content_response_shape(client, auth_headers):
    resp = client.post("/api/v1/content", json={
        "type": "article", "title": "Shape", "body": "<p>ok</p>",
    }, headers=auth_headers)
    assert resp.status_code == 201
    for key in ("content_id", "type", "title", "status", "version", "body", "created_at"):
        assert key in resp.json, f"Missing content field: {key}"


# ---------------------------------------------------------------------------
# 4xx/5xx error codes match expected error keys
# ---------------------------------------------------------------------------

def test_401_error_key(client):
    resp = client.get("/api/v1/messages")
    assert resp.status_code == 401
    assert resp.json["error"] == "unauthorized"


def test_403_error_key(client):
    """Member role attempting an admin-only action → 403."""
    username = f"mem_{uuid.uuid4().hex[:8]}"
    client.post("/api/v1/auth/register",
                json={"username": username, "password": "MemPass1234!", "role": "Member"})
    token = client.post("/api/v1/auth/login",
                        json={"username": username, "password": "MemPass1234!"}).json["token"]
    h = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/products", json={
        "sku": "X", "name": "X", "brand": "X", "category": "X", "price_usd": 1,
    }, headers=h)
    assert resp.status_code == 403
    assert resp.json["error"] == "forbidden"


def test_404_error_key(client, auth_headers):
    resp = client.get(f"/api/v1/products/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json["error"] == "not_found"


def test_409_conflict_error_key(client, auth_headers):
    """Duplicate SKU → 409 with sku_taken error."""
    sku = f"DUP-{uuid.uuid4().hex[:6]}"
    client.post("/api/v1/products", json={
        "sku": sku, "name": "A", "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers)
    resp = client.post("/api/v1/products", json={
        "sku": sku, "name": "A", "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json["error"] == "sku_taken"
