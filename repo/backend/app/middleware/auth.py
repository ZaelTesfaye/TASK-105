"""
Auth decorator — validates Bearer token and loads current_user into g.
Usage: @require_auth on any route handler.
"""
import hashlib
from functools import wraps
from datetime import datetime, timezone
from flask import request, g
from app.extensions import db
from app.models.user import User
from app.models.user import Session
from app.errors import UnauthorizedError


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def load_user_from_token() -> User | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    raw_token = auth[7:]
    token_hash = _hash_token(raw_token)
    session = db.session.get(Session, token_hash)
    if session is None:
        return None
    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    user = db.session.get(User, session.user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = load_user_from_token()
        if user is None:
            raise UnauthorizedError("unauthorized", "Authentication required")
        g.current_user = user
        return f(*args, **kwargs)
    return decorated
