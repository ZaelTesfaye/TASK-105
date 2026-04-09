"""User management service (list, get, update, delete, password change)."""
import bcrypt
import json
from datetime import datetime, timezone

from flask import g

from app.extensions import db
from app.models.user import User, ROLES
from app.models.audit import AuditLog
from app.errors import NotFoundError, ForbiddenError, ConflictError, AppError
from app.services.auth_service import AuthService


def _correlation_id() -> str:
    return getattr(g, "correlation_id", "")


class UserService:

    @staticmethod
    def _get_or_404(user_id: str) -> User:
        user = db.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFoundError("user")
        return user

    @staticmethod
    def list_users(role=None, page=1, page_size=20, include_deleted=False) -> dict:
        q = User.query
        if not include_deleted:
            q = q.filter(User.deleted_at.is_(None))
        if role:
            q = q.filter(User.role == role)
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "page": page, "page_size": page_size, "items": [u.to_dict() for u in items]}

    @staticmethod
    def get_user(user_id: str, requester: User) -> User:
        user = UserService._get_or_404(user_id)
        # Admin/Operations Manager can view any user; others can only view themselves
        if requester.role not in ("Administrator", "Operations Manager") and str(requester.user_id) != user_id:
            raise ForbiddenError("forbidden", "Cannot view this user")
        return user

    @staticmethod
    def update_user(user_id: str, data: dict, requester: User) -> User:
        user = UserService._get_or_404(user_id)

        if "role" in data:
            if requester.role != "Administrator":
                raise ForbiddenError("forbidden", "Only Administrators can change roles")
            new_role = data["role"]
            if new_role not in ROLES:
                raise AppError("invalid_role", "Invalid role", field="role")
            old_role = user.role
            user.role = new_role
            db.session.add(AuditLog(
                action_type="auth",
                actor_id=requester.user_id,
                target_type="User",
                target_id=str(user.user_id),
                before_state=json.dumps({"role": old_role}),
                after_state=json.dumps({"role": new_role}),
                correlation_id=_correlation_id(),
            ))

        if "username" in data:
            if str(requester.user_id) != user_id and requester.role != "Administrator":
                raise ForbiddenError("forbidden", "Can only change your own username")
            new_username = data["username"]
            # Ensure uniqueness (exclude current user)
            conflict = User.query.filter(
                User.username == new_username,
                User.user_id != user.user_id,
            ).first()
            if conflict:
                raise ConflictError("username_taken", "Username already in use", field="username")
            user.username = new_username

        db.session.commit()
        return user

    @staticmethod
    def change_password(user_id: str, data: dict, requester: User) -> None:
        user = UserService._get_or_404(user_id)
        if str(requester.user_id) != user_id and requester.role != "Administrator":
            raise ForbiddenError("forbidden", "Cannot change another user's password")

        new_pw = data.get("new_password", "")
        if len(new_pw) < 12:
            raise AppError("password_too_short", "Password must be at least 12 characters",
                           field="new_password", status_code=400)

        if str(requester.user_id) == user_id:
            current_pw = data.get("current_password", "")
            if not current_pw:
                raise AppError("current_password_required", "Current password is required",
                               field="current_password", status_code=400)
            # user.password_hash is decrypted by EncryptedText TypeDecorator — it's the raw bcrypt hash
            if not bcrypt.checkpw(current_pw.encode(), user.password_hash.encode()):
                raise AppError("invalid_current_password", "Current password is incorrect",
                               field="current_password", status_code=400)

        # Hash new password; EncryptedText TypeDecorator will Fernet-encrypt on write
        user.password_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(rounds=12)).decode()

        db.session.add(AuditLog(
            action_type="auth",
            actor_id=requester.user_id,
            target_type="User",
            target_id=str(user.user_id),
            after_state=json.dumps({"event": "password_changed"}),
            correlation_id=_correlation_id(),
        ))

        # Invalidate all existing sessions (forces re-login on all devices)
        AuthService.invalidate_all_sessions(user.user_id)
        db.session.commit()

    @staticmethod
    def delete_user(user_id: str) -> None:
        user = UserService._get_or_404(user_id)
        user.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
