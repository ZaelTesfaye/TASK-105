"""
Shared base utilities for models.
"""
import uuid
from sqlalchemy import TypeDecorator, String
from app import crypto


class GUID(TypeDecorator):
    """Stores UUID as TEXT in SQLite."""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value)


class EncryptedText(TypeDecorator):
    """Transparently Fernet-encrypts text columns at rest."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return crypto.encrypt(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return crypto.decrypt(value)


def new_uuid() -> str:
    return str(uuid.uuid4())
