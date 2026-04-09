"""
API functional tests for admin tickets, audit log, and health endpoints.

Covers: ticket creation, listing, status filtering, closing, audit log access,
        RBAC enforcement for tickets and audit log, and health/readiness checks.
All tests use the Flask test client against /api/v1/admin/* and related endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"


def _create_ticket(client, headers, ticket_type="moderation", **overrides):
    payload = {
        "type": ticket_type,
        "subject": f"Issue {uuid.uuid4().hex[:4]}",
        "body": "Please review this matter.",
    }
    payload.update(overrides)
    return client.post(f"{BASE}/admin/tickets", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Admin tickets
# ---------------------------------------------------------------------------

def test_create_ticket_201(client, auth_headers):
    """POST /admin/tickets returns 201 with ticket_id and status=open."""
    resp = _create_ticket(client, auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "ticket_id" in data
    assert data["status"] == "open"


def test_create_ticket_member_403(client, member_headers):
    """Member token POST /admin/tickets returns 403."""
    resp = _create_ticket(client, member_headers)
    assert resp.status_code == 403


def test_list_tickets_200(client, auth_headers):
    """GET /admin/tickets returns 200 with paginated response."""
    _create_ticket(client, auth_headers)
    resp = client.get(f"{BASE}/admin/tickets", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "total" in data or "items" in data or isinstance(data, list)


def test_list_tickets_status_filter(client, auth_headers):
    """GET /admin/tickets?status=open returns only open tickets."""
    _create_ticket(client, auth_headers)
    resp = client.get(f"{BASE}/admin/tickets?status=open", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    items = data.get("items", data) if isinstance(data, dict) else data
    assert isinstance(items, list)
    if len(items) > 0:
        assert all(t["status"] == "open" for t in items)


def test_close_ticket_200(client, auth_headers):
    """PATCH /admin/tickets/{id} with status=closed returns 200 with status=closed."""
    ticket = _create_ticket(client, auth_headers).json
    tid = ticket["ticket_id"]
    resp = client.patch(f"{BASE}/admin/tickets/{tid}", json={"status": "closed"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "closed"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def test_audit_log_admin_200(client, auth_headers):
    """GET /audit-log returns 200 with items array for admin."""
    resp = client.get(f"{BASE}/audit-log", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "items" in data


def test_audit_log_member_403(client, member_headers):
    """Member token GET /audit-log returns 403."""
    resp = client.get(f"{BASE}/audit-log", headers=member_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

def test_health_liveness_200(client):
    """GET /health returns 200 with {status: ok, db: ok, version: string}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert "db" in data
    assert "version" in data
    assert isinstance(data["version"], str)


def test_health_readiness(client):
    """GET /health/ready returns 200 or 503 — either is acceptable in test environment."""
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    assert "status" in resp.json


# ---------------------------------------------------------------------------
# Group-leader performance report (REPORT-1)
# ---------------------------------------------------------------------------

def _create_community(client, headers):
    payload = {
        "name": f"Comm {uuid.uuid4().hex[:6]}",
        "address_line1": "1 Main St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }
    resp = client.post(f"{BASE}/communities", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json["community_id"]


def test_report_admin_no_filter_200(client, auth_headers):
    """Admin GET /admin/reports/group-leader-performance (no filter) returns 200 with correct shape."""
    resp = client.get(f"{BASE}/admin/reports/group-leader-performance", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "period" in data
    assert "total_orders" in data
    assert "total_order_value_usd" in data
    assert "commission_earned_usd" in data
    assert "top_products" in data
    assert isinstance(data["top_products"], list)


def test_report_admin_with_community_id_200(client, auth_headers):
    """Admin GET /admin/reports/group-leader-performance?community_id=X returns 200 with community_id echoed."""
    comm_id = _create_community(client, auth_headers)
    resp = client.get(
        f"{BASE}/admin/reports/group-leader-performance?community_id={comm_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["community_id"] == comm_id


def test_report_admin_with_date_range_200(client, auth_headers):
    """Admin GET with from/to date params returns 200 with period echoed."""
    resp = client.get(
        f"{BASE}/admin/reports/group-leader-performance?from=2026-01-01&to=2026-03-31",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["period"]["from"] == "2026-01-01"
    assert data["period"]["to"] == "2026-03-31"


def test_report_unauthenticated_401(client):
    """Unauthenticated GET /admin/reports/group-leader-performance returns 401."""
    resp = client.get(f"{BASE}/admin/reports/group-leader-performance")
    assert resp.status_code == 401


def test_report_member_403(client, member_headers):
    """Authenticated Member GET /admin/reports/group-leader-performance returns 403."""
    resp = client.get(
        f"{BASE}/admin/reports/group-leader-performance",
        headers=member_headers,
    )
    assert resp.status_code == 403


def test_report_group_leader_own_community_200(client, auth_headers):
    """Group Leader can access the report for their bound community."""
    comm_id = _create_community(client, auth_headers)

    # Register a Group Leader via service layer (public HTTP endpoint is Member-only)
    gl_name = f"gl_{uuid.uuid4().hex[:6]}"
    with client.application.app_context():
        from app.services.auth_service import AuthService
        gl_user = AuthService.register(gl_name, "GlTestPass1!", role="Group Leader")
        gl_user_id = str(gl_user.user_id)
    gl_resp = client.post("/api/v1/auth/login", json={
        "username": gl_name, "password": "GlTestPass1!",
    })
    gl_token = gl_resp.json["token"]
    gl_headers = {"Authorization": f"Bearer {gl_token}"}

    # Bind GL to the community
    client.post(
        f"{BASE}/communities/{comm_id}/leader-binding",
        json={"user_id": gl_user_id},
        headers=auth_headers,
    )

    resp = client.get(
        f"{BASE}/admin/reports/group-leader-performance?community_id={comm_id}",
        headers=gl_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["community_id"] == comm_id


def test_report_group_leader_other_community_403(client, auth_headers):
    """Group Leader cannot access report for a community they're not bound to."""
    comm1_id = _create_community(client, auth_headers)
    comm2_id = _create_community(client, auth_headers)

    gl_name = f"gl_{uuid.uuid4().hex[:6]}"
    with client.application.app_context():
        from app.services.auth_service import AuthService
        gl_user = AuthService.register(gl_name, "GlTestPass1!", role="Group Leader")
        gl_user_id = str(gl_user.user_id)
    gl_resp = client.post("/api/v1/auth/login", json={
        "username": gl_name, "password": "GlTestPass1!",
    })
    gl_token = gl_resp.json["token"]
    gl_headers = {"Authorization": f"Bearer {gl_token}"}

    # Bind GL to comm1
    client.post(
        f"{BASE}/communities/{comm1_id}/leader-binding",
        json={"user_id": gl_user_id},
        headers=auth_headers,
    )

    # Attempt to access comm2 — should be 403
    resp = client.get(
        f"{BASE}/admin/reports/group-leader-performance?community_id={comm2_id}",
        headers=gl_headers,
    )
    assert resp.status_code == 403
