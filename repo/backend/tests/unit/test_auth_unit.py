"""
Unit tests for AuthService — all calls go directly to the service layer, no HTTP.

Covered:
  - Password length validation (too short / exactly 12)
  - Role validation (invalid role / all 6 valid roles)
  - Duplicate username conflict
  - Login happy-path returns token
  - Login wrong-password raises UnauthorizedError
  - Lockout after 5 failures; 6th attempt raises LockedError
  - Failed-attempt counter resets on successful login
  - Logout deletes Session from DB
  - Raw token is NOT stored in sessions table (only its SHA-256 hash)
"""
import hashlib
import uuid

import pytest

from app.services.auth_service import AuthService
from app.models.user import User, Session, ROLES
from app.errors import AppError, ConflictError, UnauthorizedError, LockedError
from app.extensions import db


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _u(prefix="u"):
    """Return a unique username."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _pw(suffix=""):
    """Return a 12-character password (meets minimum length)."""
    return f"ValidPass12!{suffix}"


# ---------------------------------------------------------------------------
# Registration — password validation
# ---------------------------------------------------------------------------

class TestPasswordValidation:

    def test_password_too_short(self, app):
        """AuthService.register raises AppError(error='password_too_short') for < 12 chars."""
        with app.app_context():
            with pytest.raises(AppError) as exc_info:
                AuthService.register(_u(), "short1234!")
            assert exc_info.value.error == "password_too_short"

    def test_password_exactly_12_accepted(self, app):
        """A 12-character password is accepted without error."""
        with app.app_context():
            user = AuthService.register(_u(), "ExactlyTwlv1")
            assert user.user_id is not None


# ---------------------------------------------------------------------------
# Registration — role validation
# ---------------------------------------------------------------------------

class TestRoleValidation:

    def test_invalid_role_rejected(self, app):
        """AuthService.register raises AppError(error='invalid_role') for unknown roles."""
        with app.app_context():
            with pytest.raises(AppError) as exc_info:
                AuthService.register(_u(), _pw(), role="Hacker")
            assert exc_info.value.error == "invalid_role"

    def test_all_valid_roles_accepted(self, app):
        """All six defined ROLES can be used when registering a user."""
        expected_roles = (
            "Administrator",
            "Operations Manager",
            "Moderator",
            "Group Leader",
            "Staff",
            "Member",
        )
        with app.app_context():
            for role in expected_roles:
                user = AuthService.register(_u(role.split()[0].lower()), _pw(), role=role)
                assert user.role == role


# ---------------------------------------------------------------------------
# Registration — uniqueness
# ---------------------------------------------------------------------------

class TestUsernameUniqueness:

    def test_duplicate_username_raises(self, app):
        """Second register with the same username raises ConflictError(error='username_taken')."""
        username = _u("dup")
        with app.app_context():
            AuthService.register(username, _pw())
            with pytest.raises(ConflictError) as exc_info:
                AuthService.register(username, _pw())
            assert exc_info.value.error == "username_taken"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_success_returns_token(self, app):
        """Successful login returns a dict containing a 'token' key."""
        username = _u("login")
        password = _pw()
        with app.app_context():
            AuthService.register(username, password)
            result = AuthService.login(username, password)
        assert "token" in result
        assert isinstance(result["token"], str)
        assert len(result["token"]) > 0

    def test_login_wrong_password_raises(self, app):
        """Wrong password raises UnauthorizedError."""
        username = _u("wrongpw")
        password = _pw()
        with app.app_context():
            AuthService.register(username, password)
            with pytest.raises(UnauthorizedError):
                AuthService.login(username, "WrongPass1234!")

    def test_login_lockout_after_5_failures(self, app):
        """Five consecutive wrong passwords lock the account; the 6th attempt raises LockedError."""
        username = _u("lockout")
        password = _pw()
        with app.app_context():
            AuthService.register(username, password)
            # 5 wrong attempts to trigger lockout
            for _ in range(5):
                with pytest.raises(UnauthorizedError):
                    AuthService.login(username, "BadPass111111!")
            # The 6th attempt should see a locked account
            with pytest.raises(LockedError):
                AuthService.login(username, password)

    def test_login_counter_resets_on_success(self, app):
        """4 failures followed by 1 success resets failed_attempts to 0."""
        username = _u("resetctr")
        password = _pw()
        with app.app_context():
            AuthService.register(username, password)
            # 4 wrong attempts (one short of lockout)
            for _ in range(4):
                with pytest.raises(UnauthorizedError):
                    AuthService.login(username, "BadPass111111!")
            # Correct password — should succeed and reset counter
            AuthService.login(username, password)
            user = User.query.filter_by(username=username).first()
            assert user.failed_attempts == 0


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:

    def test_logout_invalidates_token(self, app):
        """After logout, the Session row is removed from the database."""
        username = _u("logout")
        password = _pw()
        with app.app_context():
            AuthService.register(username, password)
            result = AuthService.login(username, password)
            raw_token = result["token"]
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

            # Session exists before logout
            session_before = db.session.get(Session, token_hash)
            assert session_before is not None

            AuthService.logout(raw_token)

            # Session is gone after logout
            session_after = db.session.get(Session, token_hash)
            assert session_after is None


# ---------------------------------------------------------------------------
# Token storage security
# ---------------------------------------------------------------------------

class TestTokenStorage:

    def test_token_hash_not_stored_raw(self, app):
        """The raw token string must NOT appear in any row of the sessions table."""
        username = _u("tokenhash")
        password = _pw()
        with app.app_context():
            AuthService.register(username, password)
            result = AuthService.login(username, password)
            raw_token = result["token"]

            all_sessions = Session.query.all()
            stored_hashes = [s.token_hash for s in all_sessions]

            # The raw token itself must not be stored anywhere
            assert raw_token not in stored_hashes

            # The SHA-256 hash of the raw token must be present
            expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            assert expected_hash in stored_hashes
