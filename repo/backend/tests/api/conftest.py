"""Shared fixtures for API functional tests (HTTP layer)."""
import uuid
import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


def _register_login(app, client, role="Administrator"):
    """Register a user with the given role (bypassing the HTTP endpoint for
    privileged roles, since public registration is now locked to 'Member')
    then log in and return (username, password, token)."""
    uname = f"api_{uuid.uuid4().hex[:8]}"
    pwd = "ApiTestPass1!"
    with app.app_context():
        from app.services.auth_service import AuthService
        AuthService.register(uname, pwd, role=role)
    resp = client.post("/api/v1/auth/login", json={"username": uname, "password": pwd})
    return uname, pwd, resp.json["token"]


@pytest.fixture(scope="function")
def admin_token(app, client):
    _, _, tok = _register_login(app, client, "Administrator")
    return tok


@pytest.fixture(scope="function")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
def member_token(app, client):
    _, _, tok = _register_login(app, client, "Member")
    return tok


@pytest.fixture(scope="function")
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}
