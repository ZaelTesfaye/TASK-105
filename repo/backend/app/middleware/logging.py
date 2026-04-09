"""
Structured JSON request/response logger.

Delegates redaction and logger setup to the centralized logger definition
at ``backend/logging/logger.py``.  This middleware wires the logger into
Flask's request/response lifecycle.
"""
import importlib.util
import json
import os
import time
import uuid
import logging
from flask import Flask, g, request

# Import centralized logger definition (not a package — loaded by path to
# avoid shadowing stdlib ``logging``).
_logger_spec = importlib.util.spec_from_file_location(
    "backend_logger",
    os.path.join(os.path.dirname(__file__), "..", "..", "logging", "logger.py"),
)
_logger_mod = importlib.util.module_from_spec(_logger_spec)
_logger_spec.loader.exec_module(_logger_mod)

REDACTED_KEYS = _logger_mod.REDACTED_KEYS
_redact = _logger_mod.redact


def init_logging_middleware(app: Flask) -> None:
    log_file = app.config.get("LOG_FILE", "data/logs/app.jsonl")
    log_level = app.config.get("LOG_LEVEL", "INFO")

    _logger_mod.init_app_logger(log_file, log_level)

    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    handler = logging.FileHandler(log_file)
    handler.setLevel(log_level)
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)

    @app.before_request
    def start_timer():
        g.start_time = time.time()
        g.span_id = str(uuid.uuid4())

    @app.after_request
    def log_request(response):
        duration_ms = round((time.time() - getattr(g, "start_time", time.time())) * 1000, 2)
        user = getattr(g, "current_user", None)

        entry = {
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "level": "WARN" if duration_ms > 100 else "INFO",
            "correlation_id": getattr(g, "correlation_id", ""),
            "span_id": getattr(g, "span_id", ""),
            "user_id": str(user.user_id) if user else None,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
        app.logger.info(json.dumps(entry))
        return response
