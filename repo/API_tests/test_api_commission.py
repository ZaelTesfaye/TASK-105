"""
API functional tests for commission rules and settlement endpoints.

Covers: commission rule CRUD, rate validation, idempotent settlement creation,
        dispute filing/resolving/rejecting, and settlement finalization.
All tests use the Flask test client against /api/v1/communities/{id}/commission-rules
and /api/v1/settlements/* endpoints.
"""
import uuid
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.commission import SettlementRun

BASE = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_community(client, headers):
    resp = client.post(f"{BASE}/communities", json={
        "name": f"Comm_{uuid.uuid4().hex[:6]}",
        "address_line1": "1 Oak St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["community_id"]


def _create_rule(client, headers, community_id, **overrides):
    payload = {
        "rate": 6.0,
        "floor": 0.0,
        "ceiling": 15.0,
        "settlement_cycle": "weekly",
    }
    payload.update(overrides)
    return client.post(f"{BASE}/communities/{community_id}/commission-rules",
                       json=payload, headers=headers)


def _create_settlement(client, headers, community_id, idempotency_key=None):
    if idempotency_key is None:
        idempotency_key = uuid.uuid4().hex
    return client.post(f"{BASE}/settlements", json={
        "community_id": community_id,
        "period_start": "2026-01-05",
        "period_end": "2026-01-11",
        "idempotency_key": idempotency_key,
    }, headers=headers)


# ---------------------------------------------------------------------------
# Commission rule CRUD
# ---------------------------------------------------------------------------

def test_create_rule_201(client, auth_headers):
    """POST /communities/{id}/commission-rules returns 201 with rule_id/rate/floor/ceiling."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, rate=8.0, floor=1.0, ceiling=12.0)
    assert resp.status_code == 201
    data = resp.json
    assert "rule_id" in data
    assert data["rate"] == 8.0
    assert data["floor"] == 1.0
    assert data["ceiling"] == 12.0


def test_create_rule_floor_gt_rate_400(client, auth_headers):
    """floor > rate returns 400 with error=invalid_rate_range."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, rate=6.0, floor=10.0, ceiling=15.0)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rate_range"


def test_create_rule_ceiling_above_15_400(client, auth_headers):
    """ceiling > 15.0 returns 400."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, rate=6.0, floor=0.0, ceiling=16.0)
    assert resp.status_code == 400


def test_create_rule_invalid_cycle_400(client, auth_headers):
    """settlement_cycle='monthly' returns 400."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, settlement_cycle="monthly")
    assert resp.status_code == 400


def test_update_rule_200(client, auth_headers):
    """PATCH commission rule returns 200 with updated values."""
    cid = _create_community(client, auth_headers)
    rule_id = _create_rule(client, auth_headers, cid).json["rule_id"]
    resp = client.patch(
        f"{BASE}/communities/{cid}/commission-rules/{rule_id}",
        json={"rate": 7.5, "ceiling": 12.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json["rate"] == 7.5


def test_update_rule_invalid_bounds_400(client, auth_headers):
    """PATCH making floor > rate returns 400."""
    cid = _create_community(client, auth_headers)
    rule_id = _create_rule(client, auth_headers, cid, rate=6.0, floor=0.0, ceiling=10.0).json["rule_id"]
    resp = client.patch(
        f"{BASE}/communities/{cid}/commission-rules/{rule_id}",
        json={"floor": 9.0},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rate_range"


def test_delete_rule_204(client, auth_headers):
    """DELETE commission rule returns 204."""
    cid = _create_community(client, auth_headers)
    rule_id = _create_rule(client, auth_headers, cid).json["rule_id"]
    resp = client.delete(
        f"{BASE}/communities/{cid}/commission-rules/{rule_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Settlements
# ---------------------------------------------------------------------------

def test_create_settlement_201(client, auth_headers):
    """POST /settlements returns 201 with settlement_id/status/period_start/period_end."""
    cid = _create_community(client, auth_headers)
    resp = _create_settlement(client, auth_headers, cid)
    assert resp.status_code == 201
    data = resp.json
    assert "settlement_id" in data
    assert "status" in data
    assert "period_start" in data
    assert "period_end" in data


def test_settlement_idempotent_409(client, auth_headers):
    """Same idempotency_key → 409 with the same settlement_id returned."""
    cid = _create_community(client, auth_headers)
    key = uuid.uuid4().hex
    first = _create_settlement(client, auth_headers, cid, idempotency_key=key)
    assert first.status_code == 201

    second = _create_settlement(client, auth_headers, cid, idempotency_key=key)
    assert second.status_code == 409
    assert second.json["settlement_id"] == first.json["settlement_id"]


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------

def test_dispute_within_window_201(client, auth_headers):
    """POST /settlements/{id}/disputes returns 201 with dispute_id and status=open."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Wrong amount",
        "disputed_amount": 50.0,
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "dispute_id" in data
    assert data["status"] == "open"


def test_dispute_window_expired_422(client, auth_headers, app):
    """POST dispute after 2-day window → 422 with error=dispute_window_expired."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    with app.app_context():
        s = db.session.get(SettlementRun, sid)
        assert s is not None
        s.created_at = datetime.now(timezone.utc) - timedelta(days=3)
        db.session.commit()

    resp = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Past deadline",
        "disputed_amount": 1.0,
    }, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json["error"] == "dispute_window_expired"


def test_dispute_resolve_200(client, auth_headers):
    """PATCH dispute with resolution=resolved returns 200 with status=resolved."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Test",
        "disputed_amount": 10.0,
    }, headers=auth_headers).json
    did = dispute["dispute_id"]
    resp = client.patch(f"{BASE}/settlements/{sid}/disputes/{did}", json={
        "resolution": "resolved",
        "notes": "Accepted",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "resolved"


def test_dispute_reject_200(client, auth_headers):
    """PATCH dispute with resolution=rejected returns 200 with status=rejected."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Test",
        "disputed_amount": 5.0,
    }, headers=auth_headers).json
    did = dispute["dispute_id"]
    resp = client.patch(f"{BASE}/settlements/{sid}/disputes/{did}", json={
        "resolution": "rejected",
        "notes": "Not valid",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "rejected"


# ---------------------------------------------------------------------------
# Settlement finalization
# ---------------------------------------------------------------------------

def test_finalize_settlement_blocked_422(client, auth_headers):
    """Finalizing with an open dispute returns 422 with error=settlement_blocked_by_open_dispute."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Open dispute",
        "disputed_amount": 25.0,
    }, headers=auth_headers)
    resp = client.post(f"{BASE}/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json["error"] == "settlement_blocked_by_open_dispute"


def test_finalize_settlement_ok_200(client, auth_headers):
    """After resolving all disputes, finalize returns 200 with status=completed."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Test",
        "disputed_amount": 10.0,
    }, headers=auth_headers).json
    did = dispute["dispute_id"]
    client.patch(f"{BASE}/settlements/{sid}/disputes/{did}", json={
        "resolution": "resolved",
        "notes": "Accepted",
    }, headers=auth_headers)
    resp = client.post(f"{BASE}/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "completed"


def test_finalize_no_disputes_200(client, auth_headers):
    """Finalizing a settlement with no disputes returns 200 with status=completed."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"{BASE}/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "completed"


# ---------------------------------------------------------------------------
# Settlement dispute object-level auth
# ---------------------------------------------------------------------------

def test_dispute_member_403(client, auth_headers, member_headers):
    """Member cannot file a dispute (no settlement access) → 403."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Unauthorized attempt",
        "disputed_amount": 10.0,
    }, headers=member_headers)
    assert resp.status_code == 403


def test_dispute_cross_community_gl_403(client, auth_headers):
    """Group Leader cannot file a dispute on a settlement from a community they're not bound to."""
    comm1_id = _create_community(client, auth_headers)
    comm2_id = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, comm2_id).json["settlement_id"]

    gl_name = f"gl_{uuid.uuid4().hex[:6]}"
    with client.application.app_context():
        from app.services.auth_service import AuthService
        gl_user = AuthService.register(gl_name, "GlTestPass1!", role="Group Leader")
        gl_user_id = str(gl_user.user_id)
    gl_token = client.post(f"{BASE}/auth/login", json={
        "username": gl_name, "password": "GlTestPass1!",
    }).json["token"]
    gl_headers = {"Authorization": f"Bearer {gl_token}"}

    # Bind GL to comm1, not comm2
    client.post(f"{BASE}/communities/{comm1_id}/leader-binding",
                json={"user_id": gl_user_id}, headers=auth_headers)

    resp = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Cross-community attempt",
        "disputed_amount": 5.0,
    }, headers=gl_headers)
    assert resp.status_code == 403


def test_settlement_totals_scoped_to_community_warehouses(client, auth_headers):
    """Settlement sums only issue txns from warehouses tied to that community."""
    comm1 = _create_community(client, auth_headers)
    comm2 = _create_community(client, auth_headers)
    wh1 = client.post(f"{BASE}/warehouses", json={
        "name": f"WH-{uuid.uuid4().hex[:6]}",
        "location": "A",
        "community_id": comm1,
    }, headers=auth_headers)
    wh2 = client.post(f"{BASE}/warehouses", json={
        "name": f"WH-{uuid.uuid4().hex[:6]}",
        "location": "B",
        "community_id": comm2,
    }, headers=auth_headers)
    assert wh1.status_code == 201 and wh2.status_code == 201
    w1, w2 = wh1.json["warehouse_id"], wh2.json["warehouse_id"]

    sku = f"SKU-{uuid.uuid4().hex[:8]}"
    pr = client.post(f"{BASE}/products", json={
        "sku": sku,
        "name": "Settlement Test Product",
        "brand": "B",
        "category": "C",
        "description": "",
        "price_usd": 100.0,
    }, headers=auth_headers)
    assert pr.status_code == 201
    pid = pr.json["product_id"]

    for wh, qty in ((w1, 2), (w2, 5)):
        r_resp = client.post(f"{BASE}/inventory/receipts", json={
            "sku_id": pid,
            "warehouse_id": wh,
            "quantity": 20,
            "unit_cost_usd": 1.0,
            "costing_method": "fifo",
            "occurred_at": "2026-01-05T08:00:00",
        }, headers=auth_headers)
        assert r_resp.status_code == 201
        i_resp = client.post(f"{BASE}/inventory/issues", json={
            "sku_id": pid,
            "warehouse_id": wh,
            "quantity": qty,
            "occurred_at": "2026-01-06T10:00:00",
        }, headers=auth_headers)
        assert i_resp.status_code == 201

    s_resp = client.post(f"{BASE}/settlements", json={
        "community_id": comm1,
        "period_start": "2026-01-05",
        "period_end": "2026-01-11",
        "idempotency_key": uuid.uuid4().hex,
    }, headers=auth_headers)
    assert s_resp.status_code == 201
    assert s_resp.json["total_order_value_usd"] == 200.0

    s2 = client.post(f"{BASE}/settlements", json={
        "community_id": comm2,
        "period_start": "2026-01-05",
        "period_end": "2026-01-11",
        "idempotency_key": uuid.uuid4().hex,
    }, headers=auth_headers)
    assert s2.status_code == 201
    assert s2.json["total_order_value_usd"] == 500.0
