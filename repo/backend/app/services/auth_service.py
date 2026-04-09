"""
Authentication service.
Handles registration, login (with lockout), logout, and token management.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
from flask import g, current_app

from app.extensions import db
from app.models.user import User, Session, ROLES
from app.models.audit import AuditLog
from app.errors import ConflictError, UnauthorizedError, LockedError, AppError

_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15
_TOKEN_EXPIRY_HOURS = 24


def _correlation_id() -> str:
    return getattr(g, "correlation_id", "")


class AuthService:

    @staticmethod
    def register(username: str, password: str, role: str = "Member") -> User:
        if len(password) < 12:
            raise AppError("password_too_short", "Password must be at least 12 characters",
                           field="password", status_code=400)
        if role not in ROLES:
            raise AppError("invalid_role", f"Role must be one of: {', '.join(ROLES)}", field="role", status_code=400)
        if User.query.filter_by(username=username).first():
            raise ConflictError("username_taken", "Username already in use", field="username")

        rounds = current_app.config.get("BCRYPT_ROUNDS", 12)
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()
        user = User(username=username, password_hash=hashed, role=role)
        db.session.add(user)
        db.session.flush()  # assigns user_id before audit log

        audit = AuditLog(
            action_type="auth",
            actor_id=None,
            target_type="User",
            target_id=str(user.user_id),
            after_state=json.dumps({"event": "user_registered", "username": username, "role": role}),
            correlation_id=_correlation_id(),
        )
        db.session.add(audit)
        db.session.commit()
        return user

    @staticmethod
    def login(username: str, password: str) -> dict:
        user = User.query.filter_by(username=username, deleted_at=None).first()
        if user is None:
            raise UnauthorizedError("invalid_credentials", "Invalid username or password")

        if user.is_locked():
            retry_after = user.locked_until.replace(tzinfo=timezone.utc).isoformat()
            raise LockedError(retry_after)

        # EncryptedText TypeDecorator transparently decrypts; user.password_hash is the bcrypt hash
        pw_valid = bcrypt.checkpw(password.encode(), user.password_hash.encode())
        if not pw_valid:
            user.failed_attempts += 1
            if user.failed_attempts >= _LOCKOUT_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
                audit = AuditLog(
                    action_type="auth",
                    actor_id=None,
                    target_type="User",
                    target_id=str(user.user_id),
                    after_state=json.dumps({
                        "event": "account_locked",
                        "locked_until": user.locked_until.isoformat(),
                    }),
                    correlation_id=_correlation_id(),
                )
                db.session.add(audit)
            db.session.commit()
            raise UnauthorizedError("invalid_credentials", "Invalid username or password")

        # Successful login — reset lockout state
        user.failed_attempts = 0
        user.locked_until = None

        raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRY_HOURS)

        session = Session(token_hash=token_hash, user_id=user.user_id, expires_at=expires_at)
        db.session.add(session)
        db.session.commit()

        return {
            "token": raw_token,
            "expires_at": expires_at.isoformat(),
            "user_id": str(user.user_id),
            "role": user.role,
        }

    @staticmethod
    def logout(raw_token: str) -> None:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        session = db.session.get(Session, token_hash)
        if session:
            db.session.delete(session)
            db.session.commit()

    @staticmethod
    def invalidate_all_sessions(user_id) -> None:
        Session.query.filter_by(user_id=user_id).delete()
        # Caller commits
