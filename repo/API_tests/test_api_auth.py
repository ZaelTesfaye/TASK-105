"""
API functional tests for authentication endpoints.

Covers: register, login, logout, lockout, token invalidation, and missing auth header.
All tests use the Flask test client against /api/v1/auth/* endpoints.
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
    })


def _login(client, username, password="ValidPass1234!"):
    return client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    })


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def test_register_success_201(client):
    """POST /auth/register with valid data returns 201 and expected fields."""
    username = _unique_username()
    resp = _register(client, username=username, role="Member")
    assert resp.status_code == 201
    data = resp.json
    assert "user_id" in data
    assert data["username"] == username
    assert "role" in data
    assert "created_at" in data


def test_register_password_too_short_400(client):
    """Password shorter than minimum length returns 400 with error=password_too_short."""
    resp = _register(client, username=_unique_username(), password="short1!")
    assert resp.status_code == 400
    assert resp.json["error"] == "password_too_short"


def test_register_duplicate_username_409(client):
    """Registering the same username twice returns 409 with error=username_taken."""
    username = _unique_username()
    _register(client, username=username)
    resp = _register(client, username=username)
    assert resp.status_code == 409
    assert resp.json["error"] == "username_taken"


def test_register_invalid_role_400(client):
    """Registering with an unknown role returns 400 (schema validates known roles)."""
    resp = _register(client, username=_unique_username(), role="Hacker")
    assert resp.status_code == 400


def test_register_role_field_ignored(client):
    """Supplying role='Administrator' on public registration is silently ignored; account is Member."""
    username = _unique_username()
    resp = client.post(f"{BASE}/auth/register", json={
        "username": username,
        "password": "ValidPass1234!",
        "role": "Administrator",
    })
    assert resp.status_code == 201
    assert resp.json["role"] == "Member"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success_200(client):
    """Valid credentials return 200 with a token."""
    username = _unique_username()
    _register(client, username=username)
    resp = _login(client, username)
    assert resp.status_code == 200
    assert "token" in resp.json


def test_login_wrong_password_401(client):
    """Wrong password returns 401 with error=invalid_credentials."""
    username = _unique_username()
    _register(client, username=username)
    resp = _login(client, username, password="WrongPassword99!")
    assert resp.status_code == 401
    assert resp.json["error"] == "invalid_credentials"


def test_login_nonexistent_user_401(client):
    """Logging in with an unknown username returns 401."""
    resp = _login(client, username="no_such_user_xyz_9999")
    assert resp.status_code == 401


def test_login_lockout_423(client):
    """5 bad attempts then a valid attempt returns 423 with error=account_locked and retry_after."""
    username = _unique_username()
    _register(client, username=username)
    for _ in range(5):
        _login(client, username, password="BadPassword99!")
    resp = _login(client, username)
    assert resp.status_code == 423
    assert resp.json["error"] == "account_locked"
    assert "retry_after" in resp.json


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def test_logout_204(client):
    """Valid token POST /auth/logout returns 204."""
    username = _unique_username()
    _register(client, username=username)
    token = _login(client, username).json["token"]
    resp = client.post(f"{BASE}/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204


def test_token_invalid_after_logout(client):
    """After logout, any protected endpoint returns 401 for the invalidated token."""
    username = _unique_username()
    reg_resp = _register(client, username=username)
    user_id = reg_resp.json["user_id"]
    token = _login(client, username).json["token"]

    client.post(f"{BASE}/auth/logout", headers={"Authorization": f"Bearer {token}"})

    resp = client.get(f"{BASE}/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Missing auth header
# ---------------------------------------------------------------------------

def test_require_auth_missing_header(client):
    """GET /users without Authorization header returns 401 with error=unauthorized."""
    resp = client.get(f"{BASE}/users")
    assert resp.status_code == 401
    assert resp.json["error"] == "unauthorized"
