"""Admin ticket and audit log smoke tests."""


def test_create_ticket(client, auth_headers):
    resp = client.post("/api/v1/admin/tickets", json={
        "type": "report", "subject": "Test Issue", "body": "Something happened",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["status"] == "open"


def test_list_tickets(client, auth_headers):
    client.post("/api/v1/admin/tickets", json={
        "type": "moderation", "subject": "Mod Action", "body": "Details",
    }, headers=auth_headers)
    resp = client.get("/api/v1/admin/tickets", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json


def test_close_ticket(client, auth_headers):
    create_resp = client.post("/api/v1/admin/tickets", json={
        "type": "other", "subject": "Close Me", "body": "...",
    }, headers=auth_headers)
    tid = create_resp.json["ticket_id"]
    resp = client.patch(f"/api/v1/admin/tickets/{tid}", json={
        "status": "closed", "resolution_notes": "Resolved.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "closed"


def test_audit_log_accessible_by_admin(client, auth_headers):
    resp = client.get("/api/v1/audit-log", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
