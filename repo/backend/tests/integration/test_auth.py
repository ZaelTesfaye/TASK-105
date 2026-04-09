"""Auth endpoint tests."""


def test_register_success(client):
    resp = client.post("/api/v1/auth/register", json={
        "username": "newuser", "password": "ValidPass1234!", "role": "Member",
    })
    assert resp.status_code == 201
    assert resp.json["username"] == "newuser"


def test_register_duplicate_username(client):
    client.post("/api/v1/auth/register", json={"username": "dup", "password": "ValidPass1234!"})
    resp = client.post("/api/v1/auth/register", json={"username": "dup", "password": "ValidPass1234!"})
    assert resp.status_code == 409
    assert resp.json["error"] == "username_taken"


def test_register_short_password(client):
    resp = client.post("/api/v1/auth/register", json={"username": "shortpw", "password": "short"})
    assert resp.status_code == 400
    assert resp.json["error"] == "password_too_short"


def test_register_invalid_role(client):
    resp = client.post("/api/v1/auth/register", json={
        "username": "badrole", "password": "ValidPass1234!", "role": "SuperUser",
    })
    assert resp.status_code == 400


def test_login_success(client):
    client.post("/api/v1/auth/register", json={"username": "loginuser", "password": "ValidPass1234!"})
    resp = client.post("/api/v1/auth/login", json={"username": "loginuser", "password": "ValidPass1234!"})
    assert resp.status_code == 200
    data = resp.json
    assert "token" in data
    assert "expires_at" in data
    assert "user_id" in data
    assert data["role"] == "Member"


def test_login_invalid_credentials(client):
    resp = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "WrongPass1234!"})
    assert resp.status_code == 401
    assert resp.json["error"] == "invalid_credentials"


def test_login_lockout(client):
    client.post("/api/v1/auth/register", json={"username": "lockme", "password": "ValidPass1234!"})
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "lockme", "password": "WrongPass1234!"})
    # 6th attempt with correct password still locked
    resp = client.post("/api/v1/auth/login", json={"username": "lockme", "password": "ValidPass1234!"})
    assert resp.status_code == 423
    assert resp.json["error"] == "account_locked"
    assert "retry_after" in resp.json


def test_login_lockout_exactly_5_attempts(client):
    """4 failed attempts must NOT lock the account."""
    client.post("/api/v1/auth/register", json={"username": "notlocked", "password": "ValidPass1234!"})
    for _ in range(4):
        client.post("/api/v1/auth/login", json={"username": "notlocked", "password": "WrongPass1234!"})
    # 5th attempt with correct password should succeed
    resp = client.post("/api/v1/auth/login", json={"username": "notlocked", "password": "ValidPass1234!"})
    assert resp.status_code == 200


def test_logout(client):
    client.post("/api/v1/auth/register", json={"username": "logout_u", "password": "ValidPass1234!"})
    login_resp = client.post("/api/v1/auth/login", json={"username": "logout_u", "password": "ValidPass1234!"})
    token = login_resp.json["token"]
    resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204


def test_token_invalid_after_logout(client):
    """Token must be rejected by protected endpoints after logout."""
    reg = client.post("/api/v1/auth/register", json={"username": "postlogout", "password": "ValidPass1234!"})
    user_id = reg.json["user_id"]
    token = client.post("/api/v1/auth/login", json={
        "username": "postlogout", "password": "ValidPass1234!",
    }).json["token"]

    client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})

    # Token must now be rejected
    resp = client.get(f"/api/v1/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_require_auth_missing_header(client):
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 401


def test_require_auth_malformed_header(client):
    resp = client.post("/api/v1/auth/logout", headers={"Authorization": "Token abc123"})
    assert resp.status_code == 401
