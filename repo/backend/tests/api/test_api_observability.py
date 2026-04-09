"""
API functional tests for observability: correlation ID propagation and response shapes.

Covers: X-Correlation-ID header echo/generation, health endpoint shapes,
        register/login response shapes, standard error shapes, and resource response shapes.
All tests use the Flask test client.
"""
import uuid
import pytest

BASE = "/api/v1"


def _unique_username():
    return f"user_{uuid.uuid4().hex[:8]}"


def _register(client, username=None, password="ValidPass1234!", role="Member"):
    if username is None:
        username = _unique_username()
    return client.post(f"{BASE}/auth/register", json={
        "username": username,
        "password": password,
        "role": role,
    }), username


def _login(client, username, password="ValidPass1234!"):
    return client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    })


def _admin_headers(client):
    username = _unique_username()
    password = "ValidPass1234!"
    with client.application.app_context():
        from app.services.auth_service import AuthService
        AuthService.register(username, password, role="Administrator")
    token = client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    }).json["token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Correlation ID propagation
# ---------------------------------------------------------------------------

def test_correlation_id_echoed(client):
    """Sending X-Correlation-ID is echoed back in the response header."""
    corr_id = str(uuid.uuid4())
    resp = client.get("/health", headers={"X-Correlation-ID": corr_id})
    assert resp.headers.get("X-Correlation-ID") == corr_id


def test_correlation_id_generated(client):
    """Without X-Correlation-ID header, a UUID is generated and returned."""
    resp = client.get("/health")
    corr_id = resp.headers.get("X-Correlation-ID")
    assert corr_id is not None
    assert len(corr_id) > 0
    # Validate it is a UUID
    try:
        uuid.UUID(corr_id)
    except ValueError:
        pytest.fail(f"Generated correlation ID is not a valid UUID: {corr_id}")


def test_correlation_id_on_404(client):
    """404 responses include X-Correlation-ID header."""
    resp = client.get(f"{BASE}/nonexistent_endpoint_xyz")
    assert "X-Correlation-ID" in resp.headers


# ---------------------------------------------------------------------------
# Health endpoint shapes
# ---------------------------------------------------------------------------

def test_liveness_shape(client):
    """GET /health returns status, version, db keys."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json
    assert "status" in data
    assert "version" in data
    assert "db" in data


def test_readiness_shape(client):
    """GET /health/ready returns 200 or 503 and body has status key."""
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    assert "status" in resp.json


# ---------------------------------------------------------------------------
# Auth response shapes
# ---------------------------------------------------------------------------

def test_register_response_shape(client):
    """POST /auth/register 201 response has user_id/username/role/created_at."""
    resp, _ = _register(client)
    assert resp.status_code == 201
    data = resp.json
    assert "user_id" in data
    assert "username" in data
    assert "role" in data
    assert "created_at" in data


def test_login_response_shape(client):
    """POST /auth/login 200 response has token/expires_at/user_id/role."""
    username = _unique_username()
    _register(client, username=username)
    resp = _login(client, username)
    assert resp.status_code == 200
    data = resp.json
    assert "token" in data
    assert "expires_at" in data
    assert "user_id" in data
    assert "role" in data


# ---------------------------------------------------------------------------
# Error shapes
# ---------------------------------------------------------------------------

def test_error_shape_401(client):
    """401 response has error and message keys."""
    resp = client.get(f"{BASE}/users")
    assert resp.status_code == 401
    data = resp.json
    assert "error" in data
    assert "message" in data


def test_error_shape_403(client):
    """403 response has error and message keys."""
    username = _unique_username()
    _register(client, username=username, role="Member")
    token = _login(client, username).json["token"]
    member_hdrs = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"{BASE}/users", headers=member_hdrs)
    assert resp.status_code == 403
    data = resp.json
    assert "error" in data
    assert "message" in data


def test_error_shape_404(client):
    """404 response has error and message keys."""
    headers = _admin_headers(client)
    resp = client.get(f"{BASE}/users/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
    data = resp.json
    assert "error" in data
    assert "message" in data


# ---------------------------------------------------------------------------
# Resource response shapes
# ---------------------------------------------------------------------------

def test_community_shape(client):
    """POST /communities returns community_id/name/created_at."""
    headers = _admin_headers(client)
    resp = client.post(f"{BASE}/communities", json={
        "name": f"Shape_Comm_{uuid.uuid4().hex[:4]}",
        "address_line1": "1 Shape St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json
    assert "community_id" in data
    assert "name" in data
    assert "created_at" in data


def test_product_shape(client):
    """POST /products returns product_id/sku/name/brand/category/price_usd/created_at."""
    headers = _admin_headers(client)
    resp = client.post(f"{BASE}/products", json={
        "sku": f"OBS-{uuid.uuid4().hex[:8].upper()}",
        "name": "Observability Test Product",
        "brand": "TestBrand",
        "category": "Electronics",
        "description": "Shape test",
        "price_usd": 9.99,
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json
    assert "product_id" in data
    assert "sku" in data
    assert "name" in data
    assert "brand" in data
    assert "category" in data
    assert "price_usd" in data
    assert "created_at" in data


def test_inventory_receipt_shape(client):
    """POST /inventory/receipts returns transaction_id/type/sku_id/warehouse_id/quantity_delta/occurred_at."""
    headers = _admin_headers(client)
    sku = f"OBS-INV-{uuid.uuid4().hex[:6].upper()}"
    product_resp = client.post(f"{BASE}/products", json={
        "sku": sku,
        "name": "Receipt Shape Product",
        "brand": "Brand",
        "category": "Cat",
        "description": "",
        "price_usd": 2.00,
    }, headers=headers)
    sku_id = product_resp.json["product_id"]

    wh_resp = client.post(f"{BASE}/warehouses", json={
        "name": f"OBS-WH-{uuid.uuid4().hex[:4]}",
        "location": "Dock",
    }, headers=headers)
    wh_id = wh_resp.json["warehouse_id"]

    resp = client.post(f"{BASE}/inventory/receipts", json={
        "sku_id": sku_id,
        "warehouse_id": wh_id,
        "quantity": 5,
        "unit_cost_usd": 1.50,
        "costing_method": "fifo",
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json
    assert "transaction_id" in data
    assert "type" in data
    assert "sku_id" in data
    assert "warehouse_id" in data
    assert "quantity_delta" in data
    assert "occurred_at" in data


def test_message_shape(client):
    """POST /messages returns message_id/type/sender_id/recipient_id/sent_at."""
    headers = _admin_headers(client)
    # Create recipient
    recip_username = _unique_username()
    client.post(f"{BASE}/auth/register", json={
        "username": recip_username,
        "password": "ValidPass1234!",
        "role": "Member",
    })
    recip_id = client.post(f"{BASE}/auth/register", json={
        "username": f"r_{uuid.uuid4().hex[:6]}",
        "password": "ValidPass1234!",
        "role": "Member",
    }).json["user_id"]

    resp = client.post(f"{BASE}/messages", json={
        "type": "text",
        "recipient_id": recip_id,
        "body": "Shape test message",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json
    assert "message_id" in data
    assert "type" in data
    assert "sender_id" in data
    assert "recipient_id" in data
    assert "sent_at" in data


def test_content_shape(client):
    """POST /content returns content_id/type/title/status/version/body/created_at."""
    headers = _admin_headers(client)
    resp = client.post(f"{BASE}/content", json={
        "type": "article",
        "title": "Shape Test Article",
        "body": "<p>Shape test</p>",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json
    assert "content_id" in data
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert "version" in data
    assert "body" in data
    assert "created_at" in data
