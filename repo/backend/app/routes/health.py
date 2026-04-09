from flask import Blueprint, jsonify, current_app
from app.extensions import db, scheduler

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def liveness():
    version = current_app.config.get("APP_VERSION", "unknown")
    try:
        db.session.execute(db.text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "degraded"
    return jsonify({"status": "ok", "version": version, "db": db_status})


@health_bp.get("/health/ready")
def readiness():
    errors = []
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as e:
        errors.append(f"db: {e}")

    if not scheduler.running:
        errors.append("scheduler: not running")

    if errors:
        return jsonify({"status": "not_ready", "errors": errors}), 503
    return jsonify({"status": "ready"})
