"""
Shared pytest fixtures for unit tests.
Uses in-memory SQLite so no files are created on disk.
All service calls are made directly (no HTTP) inside app.app_context().
"""
import uuid
import pytest

from app import create_app
from app.extensions import db as _db
from app.services.auth_service import AuthService


@pytest.fixture(scope="session")
def app():
    """Create a single Flask application for the entire test session."""
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    """Yield the db extension; roll back any uncommitted changes after each test."""
    with app.app_context():
        yield _db
        _db.session.rollback()


@pytest.fixture(scope="function")
def client(app):
    """Flask test client (available for tests that still need HTTP)."""
    return app.test_client()


@pytest.fixture(scope="function")
def registered_user(app):
    """
    Register a fresh user and return (user, raw_password).
    Uses a unique suffix so parallel / sequential tests never conflict.
    """
    suffix = uuid.uuid4().hex[:8]
    username = f"unituser_{suffix}"
    password = "UnitTestPass1!"
    with app.app_context():
        user = AuthService.register(username, password, role="Member")
    return user, password


@pytest.fixture(scope="function")
def auth_token(app, registered_user):
    """Login the registered_user and return the raw token string."""
    user, password = registered_user
    with app.app_context():
        result = AuthService.login(user.username, password)
    return result["token"]


@pytest.fixture(scope="function")
def auth_headers(auth_token):
    """Authorization header dict for the registered_user's token."""
    return {"Authorization": f"Bearer {auth_token}"}
