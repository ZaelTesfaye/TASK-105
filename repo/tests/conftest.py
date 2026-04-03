"""
Shared pytest fixtures.
Uses in-memory SQLite so no files are created on disk.
"""
import uuid as _uuid
import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


def _register_and_login(app, client, role="Administrator"):
    """Register a user with the given role via AuthService (bypasses HTTP lock to Member),
    then log in and return a raw token."""
    uname = f"tst_{_uuid.uuid4().hex[:8]}"
    pwd = "TestPass1234!"
    with app.app_context():
        from app.services.auth_service import AuthService
        AuthService.register(uname, pwd, role=role)
    resp = client.post("/api/v1/auth/login", json={"username": uname, "password": pwd})
    return resp.json["token"]


@pytest.fixture(scope="function")
def admin_token(app, client):
    return _register_and_login(app, client, "Administrator")


@pytest.fixture(scope="function")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
def member_token(app, client):
    return _register_and_login(app, client, "Member")


@pytest.fixture(scope="function")
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}
