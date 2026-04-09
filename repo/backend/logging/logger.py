"""
Centralized Logger definition.

This module is the single place where the application logger is configured.
It is referenced by ``app.middleware.logging`` which wires it into the Flask
request/response lifecycle.

Directory placed at ``backend/logging/`` per the mandated repository structure.
Not a Python package (no ``__init__.py``) to avoid shadowing the stdlib
``logging`` module.

Usage from application code::

    import logging
    logger = logging.getLogger("app")
    logger.info("message")

The structured JSON format, redaction rules, and file output are configured
once by ``init_app_logger()`` and apply to all handlers under the ``app``
logger name.
"""
import logging
import os


REDACTED_KEYS = frozenset({
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "body",
})


def redact(obj, depth: int = 0):
    """Recursively strip sensitive keys from dicts before logging."""
    if depth > 5:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k in REDACTED_KEYS or k.startswith("payout_") else redact(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(i, depth + 1) for i in obj]
    return obj


def init_app_logger(log_file: str, log_level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger with file handler.

    Called once during app startup by the logging middleware.
    """
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    logger = logging.getLogger("app")
    handler = logging.FileHandler(log_file)
    handler.setLevel(log_level)
    logger.addHandler(handler)
    logger.setLevel(log_level)
    return logger
