"""
Commission rules, settlement, and dispute tests.
Covers: rate-bounds validation, commission precedence, idempotent settlement,
finalization blocked by open disputes, dispute window, resolve/reject flow,
settlement audit trail.
"""
import uuid
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.commission import SettlementRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _community(client, headers):
    resp = client.post("/api/v1/communities", json={
        "name": f"Comm-{uuid.uuid4().hex[:6]}",
        "address_line1": "1 Oak St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["community_id"]


def _rule(client, headers, community_id, **kwargs):
    payload = {"rate": 6.0, "floor": 0.0, "ceiling": 15.0, "settlement_cycle": "weekly"}
    payload.update(kwargs)
    return client.post(f"/api/v1/communities/{community_id}/commission-rules",
                       json=payload, headers=headers)


def _settlement(client, headers, community_id, key=None,
                 period_start="2026-01-05", period_end="2026-01-11"):
    if key is None:
        key = uuid.uuid4().hex
    return client.post("/api/v1/settlements", json={
        "community_id": community_id,
        "period_start": period_start,
        "period_end": period_end,
        "idempotency_key": key,
    }, headers=headers)


# ---------------------------------------------------------------------------
# Commission rule CRUD
# ---------------------------------------------------------------------------

def test_create_commission_rule(client, auth_headers):
    cid = _community(client, auth_headers)
    resp = _rule(client, auth_headers, cid, rate=8.0, floor=1.0, ceiling=12.0)
    assert resp.status_code == 201
    d = resp.json
    assert d["rate"] == 8.0
    assert d["floor"] == 1.0
    assert d["ceiling"] == 12.0


def test_rule_rate_bounds_floor_gt_rate(client, auth_headers):
    """floor > rate must be rejected."""
    cid = _community(client, auth_headers)
    resp = _rule(client, auth_headers, cid, rate=5.0, floor=7.0, ceiling=15.0)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rate_range"


def test_rule_rate_bounds_ceiling_lt_rate(client, auth_headers):
    """ceiling < rate must be rejected."""
    cid = _community(client, auth_headers)
    resp = _rule(client, auth_headers, cid, rate=12.0, floor=0.0, ceiling=10.0)
    assert resp.status_code == 400


def test_rule_rate_ceiling_above_15(client, auth_headers):
    """ceiling > 15.0 must be rejected."""
    cid = _community(client, auth_headers)
    resp = _rule(client, auth_headers, cid, rate=6.0, floor=0.0, ceiling=20.0)
    assert resp.status_code == 400


def test_rule_invalid_settlement_cycle(client, auth_headers):
    cid = _community(client, auth_headers)
    resp = _rule(client, auth_headers, cid, settlement_cycle="monthly")
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_cycle"


def test_update_rule_revalidates_bounds(client, auth_headers):
    """PATCH that makes floor > rate must be rejected."""
    cid = _community(client, auth_headers)
    rule_id = _rule(client, auth_headers, cid, rate=6.0, floor=0.0, ceiling=10.0).json["rule_id"]
    resp = client.patch(
        f"/api/v1/communities/{cid}/commission-rules/{rule_id}",
        json={"floor": 9.0},  # floor=9 > rate=6 → invalid
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rate_range"


def test_update_rule_valid(client, auth_headers):
    cid = _community(client, auth_headers)
    rule_id = _rule(client, auth_headers, cid).json["rule_id"]
    resp = client.patch(
        f"/api/v1/communities/{cid}/commission-rules/{rule_id}",
        json={"rate": 7.5, "ceiling": 12.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json["rate"] == 7.5


def test_delete_rule(client, auth_headers):
    cid = _community(client, auth_headers)
    rule_id = _rule(client, auth_headers, cid).json["rule_id"]
    resp = client.delete(f"/api/v1/communities/{cid}/commission-rules/{rule_id}",
                         headers=auth_headers)
    assert resp.status_code == 204
    # Deleted rule not in list
    rules = client.get(f"/api/v1/communities/{cid}/commission-rules",
                       headers=auth_headers).json
    assert not any(r["rule_id"] == rule_id for r in rules)


# ---------------------------------------------------------------------------
# Commission precedence
# ---------------------------------------------------------------------------

def test_resolve_rate_category_rule_wins(client, auth_headers):
    """Category-specific rule takes precedence over community default."""
    from app.services.commission_service import CommissionService
    from app import create_app
    cid = _community(client, auth_headers)
    # Community default at 5%
    _rule(client, auth_headers, cid, rate=5.0)
    # Category rule at 9%
    _rule(client, auth_headers, cid, rate=9.0, product_category="Electronics")

    with client.application.app_context():
        # Category match → 9%
        assert CommissionService.resolve_rate(cid, "Electronics") == 9.0
        # Other category → community default 5%
        assert CommissionService.resolve_rate(cid, "Books") == 5.0
        # No category → community default 5%
        assert CommissionService.resolve_rate(cid) == 5.0


def test_resolve_rate_community_default(client, auth_headers):
    """Community default used when no category match."""
    from app.services.commission_service import CommissionService
    cid = _community(client, auth_headers)
    _rule(client, auth_headers, cid, rate=8.0)  # community default (no category)

    with client.application.app_context():
        assert CommissionService.resolve_rate(cid, "Anything") == 8.0


def test_resolve_rate_system_default(client, auth_headers):
    """System default 6.0% used when no rules defined."""
    from app.services.commission_service import CommissionService
    cid = _community(client, auth_headers)

    with client.application.app_context():
        assert CommissionService.resolve_rate(cid) == 6.0
        assert CommissionService.resolve_rate(cid, "Electronics") == 6.0


# ---------------------------------------------------------------------------
# Idempotent settlement
# ---------------------------------------------------------------------------

def test_settlement_idempotency_first_call_201(client, auth_headers):
    cid = _community(client, auth_headers)
    key = uuid.uuid4().hex
    resp = _settlement(client, auth_headers, cid, key=key)
    assert resp.status_code == 201
    assert resp.json["idempotency_key"] == key


def test_settlement_idempotency_duplicate_returns_409_with_body(client, auth_headers):
    """Duplicate idempotency key → 409 with the existing settlement object in body."""
    cid = _community(client, auth_headers)
    key = uuid.uuid4().hex
    first = _settlement(client, auth_headers, cid, key=key)
    second = _settlement(client, auth_headers, cid, key=key)

    assert second.status_code == 409
    # Body must include the original settlement
    assert second.json["settlement_id"] == first.json["settlement_id"]
    assert second.json["idempotency_key"] == key


def test_settlement_unique_keys_create_separately(client, auth_headers):
    cid = _community(client, auth_headers)
    r1 = _settlement(client, auth_headers, cid)
    r2 = _settlement(client, auth_headers, cid)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json["settlement_id"] != r2.json["settlement_id"]


# ---------------------------------------------------------------------------
# Finalization blocked by open disputes
# ---------------------------------------------------------------------------

def test_finalize_blocked_by_open_dispute(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]

    # File a dispute
    dispute_resp = client.post(f"/api/v1/settlements/{sid}/disputes",
                               json={"reason": "Wrong amount", "disputed_amount": 50.0},
                               headers=auth_headers)
    assert dispute_resp.status_code == 201

    # Finalization must be blocked
    fin_resp = client.post(f"/api/v1/settlements/{sid}/finalize", headers=auth_headers)
    assert fin_resp.status_code == 422
    assert fin_resp.json["error"] == "settlement_blocked_by_open_dispute"


def test_finalize_succeeds_after_dispute_resolved(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]

    dispute = client.post(f"/api/v1/settlements/{sid}/disputes",
                          json={"reason": "Test", "disputed_amount": 10.0},
                          headers=auth_headers).json
    did = dispute["dispute_id"]

    # Resolve the dispute
    client.patch(f"/api/v1/settlements/{sid}/disputes/{did}",
                 json={"resolution": "resolved", "notes": "Accepted"},
                 headers=auth_headers)

    # Now finalize should work
    fin_resp = client.post(f"/api/v1/settlements/{sid}/finalize", headers=auth_headers)
    assert fin_resp.status_code == 200
    assert fin_resp.json["status"] == "completed"
    assert fin_resp.json["finalized_at"] is not None


def test_finalize_no_disputes(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"/api/v1/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "completed"


# ---------------------------------------------------------------------------
# Dispute window
# ---------------------------------------------------------------------------

def test_dispute_filed_within_window(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"/api/v1/settlements/{sid}/disputes",
                       json={"reason": "Overcharge", "disputed_amount": 25.0},
                       headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["status"] == "open"


def test_dispute_window_expired_422(client, auth_headers, app):
    """POST dispute after the 2-day window (from created_at) → 422 dispute_window_expired."""
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]

    with app.app_context():
        s = db.session.get(SettlementRun, sid)
        assert s is not None
        s.created_at = datetime.now(timezone.utc) - timedelta(days=3)
        db.session.commit()

    resp = client.post(
        f"/api/v1/settlements/{sid}/disputes",
        json={"reason": "Too late", "disputed_amount": 1.0},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json["error"] == "dispute_window_expired"


def test_dispute_invalid_resolution(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"/api/v1/settlements/{sid}/disputes",
                          json={"reason": "Test", "disputed_amount": 1.0},
                          headers=auth_headers).json
    did = dispute["dispute_id"]
    resp = client.patch(f"/api/v1/settlements/{sid}/disputes/{did}",
                        json={"resolution": "approved"},  # invalid
                        headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_resolution"


def test_dispute_rejected(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"/api/v1/settlements/{sid}/disputes",
                          json={"reason": "Test", "disputed_amount": 5.0},
                          headers=auth_headers).json
    did = dispute["dispute_id"]
    resp = client.patch(f"/api/v1/settlements/{sid}/disputes/{did}",
                        json={"resolution": "rejected", "notes": "Not valid"},
                        headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "rejected"


# ---------------------------------------------------------------------------
# Group Leader scoping for commission rules
# ---------------------------------------------------------------------------

def test_group_leader_cannot_create_rule(client):
    import uuid as _uuid
    # Register via AuthService — public HTTP endpoint locks role to Member
    gl_name = f"gl_{_uuid.uuid4().hex[:8]}"
    adm_name = f"adm_{_uuid.uuid4().hex[:6]}"
    with client.application.app_context():
        from app.services.auth_service import AuthService
        AuthService.register(gl_name, "ValidPass1234!", role="Group Leader")
        AuthService.register(adm_name, "AdminPass1234!", role="Administrator")

    token = client.post("/api/v1/auth/login", json={
        "username": gl_name, "password": "ValidPass1234!",
    }).json["token"]
    gl_headers = {"Authorization": f"Bearer {token}"}

    adm_token = client.post("/api/v1/auth/login", json={
        "username": adm_name, "password": "AdminPass1234!",
    }).json["token"]
    adm_headers = {"Authorization": f"Bearer {adm_token}"}

    cid = _community(client, adm_headers)
    resp = _rule(client, gl_headers, cid)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Settlement audit trail
# ---------------------------------------------------------------------------

def test_create_settlement_writes_audit_log(client, auth_headers):
    """create_settlement must append an AuditLog row with action_type='settlement'."""
    from app.models.audit import AuditLog
    cid = _community(client, auth_headers)
    resp = _settlement(client, auth_headers, cid)
    assert resp.status_code == 201
    sid = resp.json["settlement_id"]
    with client.application.app_context():
        log = AuditLog.query.filter_by(
            action_type="settlement", target_type="settlement_run", target_id=sid
        ).first()
        assert log is not None, "AuditLog row missing for create_settlement"
        import json
        after = json.loads(log.after_state)
        assert after["status"] == "pending"


def test_file_dispute_writes_audit_log(client, auth_headers):
    """file_dispute must append an AuditLog row with action_type='settlement'."""
    from app.models.audit import AuditLog
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    dispute_resp = client.post(
        f"/api/v1/settlements/{sid}/disputes",
        json={"reason": "Audit test", "disputed_amount": 10.0},
        headers=auth_headers,
    )
    assert dispute_resp.status_code == 201
    did = dispute_resp.json["dispute_id"]
    with client.application.app_context():
        log = AuditLog.query.filter_by(
            action_type="settlement", target_type="settlement_dispute", target_id=did
        ).first()
        assert log is not None, "AuditLog row missing for file_dispute"


def test_resolve_dispute_writes_audit_log(client, auth_headers):
    """resolve_dispute must append an AuditLog row with action_type='settlement'."""
    import json
    from app.models.audit import AuditLog
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    did = client.post(
        f"/api/v1/settlements/{sid}/disputes",
        json={"reason": "Audit test", "disputed_amount": 5.0},
        headers=auth_headers,
    ).json["dispute_id"]
    client.patch(
        f"/api/v1/settlements/{sid}/disputes/{did}",
        json={"resolution": "resolved", "notes": "OK"},
        headers=auth_headers,
    )
    with client.application.app_context():
        logs = AuditLog.query.filter_by(
            action_type="settlement", target_type="settlement_dispute", target_id=did
        ).all()
        # Two rows expected: file + resolve
        assert len(logs) == 2, f"Expected 2 audit rows for dispute {did}, got {len(logs)}"
        resolutions = [json.loads(l.after_state)["status"] for l in logs
                       if l.after_state and "status" in json.loads(l.after_state)]
        assert "resolved" in resolutions


def test_finalize_writes_audit_log(client, auth_headers):
    """finalize must append an AuditLog row with action_type='settlement' and status=completed."""
    from app.models.audit import AuditLog
    import json
    cid = _community(client, auth_headers)
    sid = _settlement(client, auth_headers, cid).json["settlement_id"]
    client.post(f"/api/v1/settlements/{sid}/finalize", headers=auth_headers)
    with client.application.app_context():
        logs = AuditLog.query.filter_by(
            action_type="settlement", target_type="settlement_run", target_id=sid
        ).all()
        assert len(logs) == 2, f"Expected 2 audit rows (create+finalize) for {sid}"
        statuses = [json.loads(l.after_state)["status"] for l in logs
                    if l.after_state and "status" in json.loads(l.after_state)]
        assert "completed" in statuses


# ---------------------------------------------------------------------------
# Settlement cycle enforcement (Fix 3)
# ---------------------------------------------------------------------------

def test_settlement_wrong_duration_rejected(client, auth_headers):
    """Settlement period that doesn't match cycle duration is rejected."""
    cid = _community(client, auth_headers)
    _rule(client, auth_headers, cid, settlement_cycle="weekly")
    # 10 days instead of 7
    resp = _settlement(client, auth_headers, cid,
                       period_start="2026-01-05", period_end="2026-01-14")
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_settlement_period"


def test_settlement_biweekly_cycle_enforced(client, auth_headers):
    """Biweekly rule requires exactly 14-day period."""
    cid = _community(client, auth_headers)
    _rule(client, auth_headers, cid, settlement_cycle="biweekly")
    # 7 days (weekly) → rejected for biweekly
    resp = _settlement(client, auth_headers, cid,
                       period_start="2026-01-05", period_end="2026-01-11")
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_settlement_period"


def test_settlement_biweekly_correct_period(client, auth_headers):
    """Biweekly settlement with correct 14-day period succeeds."""
    cid = _community(client, auth_headers)
    _rule(client, auth_headers, cid, settlement_cycle="biweekly")
    # Monday to Sunday, 14 days inclusive
    resp = _settlement(client, auth_headers, cid,
                       period_start="2026-01-05", period_end="2026-01-18")
    assert resp.status_code == 201


def test_settlement_must_start_on_monday(client, auth_headers):
    """Settlement period must start on a Monday."""
    cid = _community(client, auth_headers)
    _rule(client, auth_headers, cid, settlement_cycle="weekly")
    # Wednesday to Tuesday (7 days, but wrong alignment)
    resp = _settlement(client, auth_headers, cid,
                       period_start="2026-01-07", period_end="2026-01-13")
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_settlement_period"
