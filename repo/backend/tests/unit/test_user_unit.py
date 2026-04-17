"""
Unit tests for UserService — all calls go directly to the service layer, no HTTP.

Covered:
  - User retrieval by ID (found and not found)
  - User update with valid and invalid payloads
  - Password change with correct and incorrect current password
  - User deletion and idempotency (deleting already-deleted user)
"""
import uuid

import pytest

from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.errors import NotFoundError, ForbiddenError, AppError
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _u(prefix="usrsvc"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _pw():
    return "ValidPass1234!"


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------

class TestGetUser:

    def test_get_user_found(self, app):
        """UserService.get_user returns the user when the requester is an Admin."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            result = UserService.get_user(str(user.user_id), admin)
            assert str(result.user_id) == str(user.user_id)

    def test_get_user_not_found(self, app):
        """UserService.get_user raises NotFoundError for a non-existent user_id."""
        with app.app_context():
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            with pytest.raises(NotFoundError):
                UserService.get_user(uuid.uuid4().hex, admin)

    def test_get_user_self_access(self, app):
        """A Member can view their own profile."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            result = UserService.get_user(str(user.user_id), user)
            assert str(result.user_id) == str(user.user_id)

    def test_get_user_other_forbidden(self, app):
        """A Member cannot view another user's profile."""
        with app.app_context():
            user1 = AuthService.register(_u("m1"), _pw(), role="Member")
            user2 = AuthService.register(_u("m2"), _pw(), role="Member")
            with pytest.raises(ForbiddenError):
                UserService.get_user(str(user1.user_id), user2)


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------

class TestUpdateUser:

    def test_update_username_valid(self, app):
        """Admin can update a user's username."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            new_name = _u("renamed")
            updated = UserService.update_user(str(user.user_id), {"username": new_name}, admin)
            assert updated.username == new_name

    def test_update_role_by_admin(self, app):
        """Admin can change a user's role."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            updated = UserService.update_user(str(user.user_id), {"role": "Staff"}, admin)
            assert updated.role == "Staff"

    def test_update_role_by_non_admin_forbidden(self, app):
        """Non-admin cannot change roles."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            ops = AuthService.register(_u("ops"), _pw(), role="Operations Manager")
            with pytest.raises(ForbiddenError):
                UserService.update_user(str(user.user_id), {"role": "Staff"}, ops)

    def test_update_invalid_role(self, app):
        """Setting an invalid role raises AppError."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            with pytest.raises(AppError) as exc_info:
                UserService.update_user(str(user.user_id), {"role": "Hacker"}, admin)
            assert exc_info.value.error == "invalid_role"


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------

class TestChangePassword:

    def test_change_password_correct_current(self, app):
        """Password change succeeds when current_password is correct."""
        password = _pw()
        new_pw = "NewSecurePass1!"
        with app.app_context():
            user = AuthService.register(_u(), password, role="Member")
            UserService.change_password(
                str(user.user_id),
                {"current_password": password, "new_password": new_pw},
                user,
            )
            # Verify new password works via login
            result = AuthService.login(user.username, new_pw)
            assert "token" in result

    def test_change_password_incorrect_current(self, app):
        """Password change fails with wrong current_password."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            with pytest.raises(AppError) as exc_info:
                UserService.change_password(
                    str(user.user_id),
                    {"current_password": "WrongPass1234!", "new_password": "AnotherPass12!"},
                    user,
                )
            assert exc_info.value.error == "invalid_current_password"

    def test_change_password_too_short(self, app):
        """Password shorter than 12 chars is rejected."""
        password = _pw()
        with app.app_context():
            user = AuthService.register(_u(), password, role="Member")
            with pytest.raises(AppError) as exc_info:
                UserService.change_password(
                    str(user.user_id),
                    {"current_password": password, "new_password": "short"},
                    user,
                )
            assert exc_info.value.error == "password_too_short"

    def test_admin_can_change_other_password(self, app):
        """Admin can change another user's password without providing current_password."""
        new_pw = "AdminSetPass1!!"
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            username = user.username
            UserService.change_password(
                str(user.user_id),
                {"new_password": new_pw},
                admin,
            )
            result = AuthService.login(username, new_pw)
            assert "token" in result


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------

class TestDeleteUser:

    def test_delete_user(self, app):
        """Deleting a user sets deleted_at; subsequent get raises NotFoundError."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            admin = AuthService.register(_u("adm"), _pw(), role="Administrator")
            user_id = str(user.user_id)
            UserService.delete_user(user_id)
            with pytest.raises(NotFoundError):
                UserService.get_user(user_id, admin)

    def test_delete_user_idempotent(self, app):
        """Deleting an already-deleted user raises NotFoundError (soft-delete guard)."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            user_id = str(user.user_id)
            UserService.delete_user(user_id)
            with pytest.raises(NotFoundError):
                UserService.delete_user(user_id)
