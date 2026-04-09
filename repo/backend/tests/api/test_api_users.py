"""
API functional tests for user management endpoints.

Covers: list users, get user, role/username changes, password changes,
        delete user, RBAC enforcement, and post-delete login rejection.
All tests use the Flask test client against /api/v1/users/* endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"


def _unique_username():
    return f"user_{uuid.uuid4().hex[:8]}"


def _register_and_login(client, role="Member", password="ValidPass1234!"):
    """Register a user and return (user_id, username, password, headers).
    Non-Member roles are created via the service layer because public
    registration is restricted to 'Member' accounts."""
    username = _unique_username()
    if role == "Member":
        reg = client.post(f"{BASE}/auth/register", json={
            "username": username,
            "password": password,
        })
        assert reg.status_code == 201
        user_id = reg.json["user_id"]
    else:
        with client.application.app_context():
            from app.services.auth_service import AuthService
            user = AuthService.register(username, password, role=role)
            user_id = str(user.user_id)
    login_resp = client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    })
    token = login_resp.json["token"]
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, username, password, headers


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------

def test_list_users_requires_auth(client):
    """GET /users without token returns 401."""
    resp = client.get(f"{BASE}/users")
    assert resp.status_code == 401


def test_list_users_member_forbidden(client, member_headers):
    """Member token attempting GET /users returns 403."""
    resp = client.get(f"{BASE}/users", headers=member_headers)
    assert resp.status_code == 403


def test_list_users_admin_ok(client, auth_headers):
    """Admin GET /users returns 200 with paginated body containing total/page/items."""
    resp = client.get(f"{BASE}/users", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "total" in data
    assert "page" in data
    assert "items" in data


def test_list_users_role_filter(client, auth_headers):
    """GET /users?role=Group+Leader returns only Group Leader users."""
    # Register a Group Leader via service layer (public HTTP endpoint is Member-only)
    gl_username = _unique_username()
    with client.application.app_context():
        from app.services.auth_service import AuthService
        AuthService.register(gl_username, "ValidPass1234!", role="Group Leader")

    resp = client.get(f"{BASE}/users?role=Group+Leader", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json["items"]
    assert len(items) >= 1
    assert all(u["role"] == "Group Leader" for u in items)


# ---------------------------------------------------------------------------
# Get user
# ---------------------------------------------------------------------------

def test_get_user_self(client):
    """User can GET their own profile and receives 200."""
    user_id, _, _, headers = _register_and_login(client)
    resp = client.get(f"{BASE}/users/{user_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json["user_id"] == user_id


def test_get_user_admin_views_any(client, auth_headers):
    """Admin can GET any user's profile."""
    user_id, _, _, _ = _register_and_login(client)
    resp = client.get(f"{BASE}/users/{user_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["user_id"] == user_id


def test_get_user_member_cannot_view_other(client):
    """Member cannot view another user's profile — returns 403."""
    other_user_id, _, _, _ = _register_and_login(client)
    _, _, _, member_hdrs = _register_and_login(client, role="Member")
    resp = client.get(f"{BASE}/users/{other_user_id}", headers=member_hdrs)
    assert resp.status_code == 403


def test_get_user_not_found(client, auth_headers):
    """GET /users/{random_uuid} returns 404 with error=not_found."""
    random_id = str(uuid.uuid4())
    resp = client.get(f"{BASE}/users/{random_id}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json["error"] == "not_found"


# ---------------------------------------------------------------------------
# Update user
# ---------------------------------------------------------------------------

def test_change_role_admin_ok(client, auth_headers):
    """Admin PATCH /users/{id} with role returns 200 and updated role."""
    user_id, _, _, _ = _register_and_login(client)
    resp = client.patch(f"{BASE}/users/{user_id}", json={"role": "Moderator"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["role"] == "Moderator"


def test_change_role_member_forbidden(client):
    """Member trying to change own role returns 403."""
    user_id, _, _, headers = _register_and_login(client, role="Member")
    resp = client.patch(f"{BASE}/users/{user_id}", json={"role": "Administrator"}, headers=headers)
    assert resp.status_code == 403


def test_change_username_self_ok(client):
    """User PATCH /users/{own_id} with a new unique username returns 200."""
    user_id, _, _, headers = _register_and_login(client)
    new_username = _unique_username()
    resp = client.patch(f"{BASE}/users/{user_id}", json={"username": new_username}, headers=headers)
    assert resp.status_code == 200
    assert resp.json["username"] == new_username


def test_change_username_duplicate_409(client, auth_headers):
    """Changing to an already-taken username returns 409."""
    user_id_a, username_a, _, _ = _register_and_login(client)
    user_id_b, _, _, headers_b = _register_and_login(client)
    resp = client.patch(f"{BASE}/users/{user_id_b}", json={"username": username_a}, headers=auth_headers)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

def test_change_password_success_204(client):
    """PATCH /users/{id}/password with correct current_password returns 204."""
    user_id, _, password, headers = _register_and_login(client)
    resp = client.patch(f"{BASE}/users/{user_id}/password", json={
        "current_password": password,
        "new_password": "NewValidPass99!",
    }, headers=headers)
    assert resp.status_code == 204


def test_change_password_wrong_current_401(client):
    """Wrong current_password returns 400 invalid_current_password."""
    user_id, _, _, headers = _register_and_login(client)
    resp = client.patch(f"{BASE}/users/{user_id}/password", json={
        "current_password": "WrongCurrentPwd99!",
        "new_password": "NewValidPass99!",
    }, headers=headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_current_password"


def test_change_password_too_short_400(client):
    """new_password shorter than minimum returns 400."""
    user_id, _, password, headers = _register_and_login(client)
    resp = client.patch(f"{BASE}/users/{user_id}/password", json={
        "current_password": password,
        "new_password": "short",
    }, headers=headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Delete user
# ---------------------------------------------------------------------------

def test_delete_user_admin_204(client, auth_headers):
    """Admin DELETE /users/{id} returns 204."""
    user_id, _, _, _ = _register_and_login(client)
    resp = client.delete(f"{BASE}/users/{user_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_user_member_forbidden(client):
    """Member DELETE /users/{id} returns 403."""
    other_id, _, _, _ = _register_and_login(client)
    _, _, _, member_hdrs = _register_and_login(client, role="Member")
    resp = client.delete(f"{BASE}/users/{other_id}", headers=member_hdrs)
    assert resp.status_code == 403


def test_deleted_user_cannot_login(client, auth_headers):
    """After an admin deletes a user, that user's login attempt returns 401."""
    username = _unique_username()
    password = "ValidPass1234!"
    reg = client.post(f"{BASE}/auth/register", json={
        "username": username,
        "password": password,
        "role": "Member",
    })
    user_id = reg.json["user_id"]

    del_resp = client.delete(f"{BASE}/users/{user_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    login_resp = client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    })
    assert login_resp.status_code == 401
