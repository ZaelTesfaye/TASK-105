"""
User management endpoint tests.
Covers RBAC enforcement, row-level scoping (Member/Group Leader), and
sensitive-action guards (password change, role assignment, soft delete).
"""
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_login(client, role="Member", password="ValidPass1234!"):
    """Register a user with a unique username and return (user_id, token).
    Member role uses the public HTTP endpoint; privileged roles use AuthService
    directly because the public endpoint is locked to 'Member'."""
    username = f"u_{uuid.uuid4().hex[:10]}"
    if role == "Member":
        reg = client.post("/api/v1/auth/register", json={
            "username": username, "password": password,
        })
        assert reg.status_code == 201, reg.json
        user_id = reg.json["user_id"]
    else:
        with client.application.app_context():
            from app.services.auth_service import AuthService
            user = AuthService.register(username, password, role=role)
            user_id = str(user.user_id)
    token = client.post("/api/v1/auth/login", json={
        "username": username, "password": password,
    }).json["token"]
    return user_id, token


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /users  (list) — Admin / Operations Manager only
# ---------------------------------------------------------------------------

def test_list_users_unauthenticated(client):
    resp = client.get("/api/v1/users")
    assert resp.status_code == 401


def test_list_users_member_forbidden(client):
    _, token = _register_login(client, role="Member")
    resp = client.get("/api/v1/users", headers=_headers(token))
    assert resp.status_code == 403


def test_list_users_group_leader_forbidden(client):
    _, token = _register_login(client, role="Group Leader")
    resp = client.get("/api/v1/users", headers=_headers(token))
    assert resp.status_code == 403


def test_list_users_admin_ok(client):
    _, token = _register_login(client, role="Administrator")
    resp = client.get("/api/v1/users", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json
    assert "items" in data
    assert "total" in data
    assert "page" in data


def test_list_users_ops_manager_ok(client):
    _, token = _register_login(client, role="Operations Manager")
    resp = client.get("/api/v1/users", headers=_headers(token))
    assert resp.status_code == 200


def test_list_users_role_filter(client):
    _, token = _register_login(client, role="Administrator")
    resp = client.get("/api/v1/users?role=Member", headers=_headers(token))
    assert resp.status_code == 200
    for item in resp.json["items"]:
        assert item["role"] == "Member"


def test_list_users_pagination(client):
    _, token = _register_login(client, role="Administrator")
    resp = client.get("/api/v1/users?page=1&page_size=2", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json["items"]) <= 2


# ---------------------------------------------------------------------------
# GET /users/{user_id} — self or Admin/OpsMgr
# ---------------------------------------------------------------------------

def test_get_user_self(client):
    user_id, token = _register_login(client)
    resp = client.get(f"/api/v1/users/{user_id}", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json["user_id"] == user_id


def test_get_user_member_cannot_view_other(client):
    """Row-level scoping: Member cannot view another user's profile."""
    other_id, _ = _register_login(client)
    _, token = _register_login(client)
    resp = client.get(f"/api/v1/users/{other_id}", headers=_headers(token))
    assert resp.status_code == 403


def test_get_user_group_leader_cannot_view_other(client):
    """Group Leader cannot view other users (they are not Admin/OpsMgr)."""
    other_id, _ = _register_login(client)
    _, token = _register_login(client, role="Group Leader")
    resp = client.get(f"/api/v1/users/{other_id}", headers=_headers(token))
    assert resp.status_code == 403


def test_get_user_admin_can_view_any(client):
    other_id, _ = _register_login(client)
    _, admin_token = _register_login(client, role="Administrator")
    resp = client.get(f"/api/v1/users/{other_id}", headers=_headers(admin_token))
    assert resp.status_code == 200


def test_get_user_not_found(client):
    _, token = _register_login(client, role="Administrator")
    resp = client.get(f"/api/v1/users/{uuid.uuid4()}", headers=_headers(token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /users/{user_id} — role change: Admin only; username: self or Admin
# ---------------------------------------------------------------------------

def test_change_role_requires_admin(client):
    user_id, token = _register_login(client, role="Moderator")
    resp = client.patch(f"/api/v1/users/{user_id}", json={"role": "Staff"}, headers=_headers(token))
    assert resp.status_code == 403


def test_ops_manager_cannot_change_role(client):
    user_id, _ = _register_login(client)
    _, ops_token = _register_login(client, role="Operations Manager")
    resp = client.patch(f"/api/v1/users/{user_id}", json={"role": "Staff"}, headers=_headers(ops_token))
    assert resp.status_code == 403


def test_admin_can_change_role(client):
    user_id, _ = _register_login(client)
    _, admin_token = _register_login(client, role="Administrator")
    resp = client.patch(f"/api/v1/users/{user_id}", json={"role": "Staff"}, headers=_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json["role"] == "Staff"


def test_change_role_invalid_value(client):
    user_id, _ = _register_login(client)
    _, admin_token = _register_login(client, role="Administrator")
    resp = client.patch(f"/api/v1/users/{user_id}", json={"role": "Ghost"}, headers=_headers(admin_token))
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_role"


def test_user_can_change_own_username(client):
    user_id, token = _register_login(client)
    new_name = f"renamed_{uuid.uuid4().hex[:6]}"
    resp = client.patch(f"/api/v1/users/{user_id}", json={"username": new_name}, headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json["username"] == new_name


def test_member_cannot_change_other_username(client):
    other_id, _ = _register_login(client)
    _, token = _register_login(client)
    resp = client.patch(f"/api/v1/users/{other_id}", json={"username": "hacked"}, headers=_headers(token))
    assert resp.status_code == 403


def test_update_username_uniqueness_enforced(client):
    """Changing to an already-taken username must return 409, not a DB error."""
    user_id1, _ = _register_login(client)
    # Get user1's username
    _, admin_token = _register_login(client, role="Administrator")
    u1 = client.get(f"/api/v1/users/{user_id1}", headers=_headers(admin_token)).json
    user_id2, token2 = _register_login(client)
    resp = client.patch(f"/api/v1/users/{user_id2}", json={"username": u1["username"]}, headers=_headers(admin_token))
    assert resp.status_code == 409
    assert resp.json["error"] == "username_taken"


# ---------------------------------------------------------------------------
# PATCH /users/{user_id}/password
# ---------------------------------------------------------------------------

def test_change_password_self_success(client):
    user_id, token = _register_login(client, password="OldValidPass1234!")
    resp = client.patch(f"/api/v1/users/{user_id}/password", json={
        "current_password": "OldValidPass1234!",
        "new_password": "NewValidPass1234!",
    }, headers=_headers(token))
    assert resp.status_code == 204


def test_change_password_invalidates_old_token(client):
    """After password change, the previous token must be rejected."""
    user_id, token = _register_login(client, password="OldValidPass1234!")
    client.patch(f"/api/v1/users/{user_id}/password", json={
        "current_password": "OldValidPass1234!",
        "new_password": "NewValidPass5678!",
    }, headers=_headers(token))
    # Old token should now be invalid
    resp = client.get(f"/api/v1/users/{user_id}", headers=_headers(token))
    assert resp.status_code == 401


def test_change_password_wrong_current(client):
    user_id, token = _register_login(client)
    resp = client.patch(f"/api/v1/users/{user_id}/password", json={
        "current_password": "CompletelyWrong!!",
        "new_password": "NewValidPass1234!",
    }, headers=_headers(token))
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_current_password"


def test_change_password_missing_current(client):
    user_id, token = _register_login(client)
    resp = client.patch(f"/api/v1/users/{user_id}/password", json={
        "new_password": "NewValidPass1234!",
    }, headers=_headers(token))
    assert resp.status_code == 400
    assert resp.json["error"] == "current_password_required"


def test_change_password_too_short(client):
    user_id, token = _register_login(client)
    resp = client.patch(f"/api/v1/users/{user_id}/password", json={
        "current_password": "ValidPass1234!",
        "new_password": "short",
    }, headers=_headers(token))
    assert resp.status_code == 400
    assert resp.json["error"] == "password_too_short"


def test_change_password_other_member_forbidden(client):
    other_id, _ = _register_login(client)
    _, token = _register_login(client)
    resp = client.patch(f"/api/v1/users/{other_id}/password", json={
        "new_password": "NewValidPass1234!",
    }, headers=_headers(token))
    assert resp.status_code == 403


def test_admin_can_change_other_password_without_current(client):
    """Admin can reset any user's password without supplying current_password."""
    user_id, _ = _register_login(client)
    _, admin_token = _register_login(client, role="Administrator")
    resp = client.patch(f"/api/v1/users/{user_id}/password", json={
        "new_password": "AdminResetPass1234!",
    }, headers=_headers(admin_token))
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# DELETE /users/{user_id} — Admin only, soft delete
# ---------------------------------------------------------------------------

def test_delete_user_requires_admin(client):
    user_id, token = _register_login(client)
    resp = client.delete(f"/api/v1/users/{user_id}", headers=_headers(token))
    assert resp.status_code == 403


def test_ops_manager_cannot_delete(client):
    user_id, _ = _register_login(client)
    _, ops_token = _register_login(client, role="Operations Manager")
    resp = client.delete(f"/api/v1/users/{user_id}", headers=_headers(ops_token))
    assert resp.status_code == 403


def test_admin_soft_deletes_user(client):
    user_id, _ = _register_login(client)
    _, admin_token = _register_login(client, role="Administrator")
    resp = client.delete(f"/api/v1/users/{user_id}", headers=_headers(admin_token))
    assert resp.status_code == 204
    # User no longer visible
    resp2 = client.get(f"/api/v1/users/{user_id}", headers=_headers(admin_token))
    assert resp2.status_code == 404


def test_deleted_user_cannot_login(client):
    user_id, _ = _register_login(client, password="ValidPass1234!")
    # Need username — fetch it first
    _, admin_token = _register_login(client, role="Administrator")
    user_data = client.get(f"/api/v1/users/{user_id}", headers=_headers(admin_token)).json
    username = user_data["username"]

    client.delete(f"/api/v1/users/{user_id}", headers=_headers(admin_token))

    resp = client.post("/api/v1/auth/login", json={
        "username": username, "password": "ValidPass1234!",
    })
    assert resp.status_code == 401
