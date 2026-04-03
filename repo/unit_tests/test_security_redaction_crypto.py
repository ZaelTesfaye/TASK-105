"""Security-focused tests: structured-log redaction helpers and encryption at rest."""
import uuid

import pytest
from sqlalchemy import text

from app.middleware.logging import REDACTED_KEYS, _redact
from app.extensions import db
from app.services.auth_service import AuthService


def test_redact_masks_password_and_message_body():
    payload = {
        "username": "u1",
        "password": "SecretPass1234!",
        "body": "hello world",
        "nested": {"new_password": "x", "payout_iban": "DE00"},
        "ok": 1,
    }
    out = _redact(payload)
    assert out["password"] == "[REDACTED]"
    assert out["body"] == "[REDACTED]"
    assert out["nested"]["new_password"] == "[REDACTED]"
    assert out["nested"]["payout_iban"] == "[REDACTED]"
    assert out["username"] == "u1"
    assert out["ok"] == 1


def test_redact_password_hash_key():
    assert _redact({"password_hash": "$2b$not_real"})["password_hash"] == "[REDACTED]"
    assert "password_hash" in REDACTED_KEYS


def test_password_encrypted_at_rest_raw_sql(app):
    """ORM loads decrypted bcrypt hash; raw SQL must show Fernet ciphertext, not $2b$-style bcrypt."""
    with app.app_context():
        pwd = "EncryptionTestPass1234!"
        AuthService.register(f"enc_{uuid.uuid4().hex[:8]}", pwd, role="Member")
        db.session.commit()
        raw = db.session.execute(text("SELECT password_hash FROM users LIMIT 1")).scalar()
    assert raw is not None
    assert isinstance(raw, str)
    assert not raw.startswith("$2")
    assert raw.startswith("gAAAAA")
