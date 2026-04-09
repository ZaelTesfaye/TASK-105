"""Audit log query service."""
from datetime import datetime

from app.extensions import db
from app.models.audit import AuditLog


class AuditService:

    @staticmethod
    def query(params: dict) -> dict:
        q = AuditLog.query
        if params.get("action_type"):
            q = q.filter(AuditLog.action_type == params["action_type"])
        if params.get("user_id"):
            q = q.filter(AuditLog.actor_id == params["user_id"])
        if params.get("from"):
            q = q.filter(AuditLog.occurred_at >= datetime.fromisoformat(params["from"]))
        if params.get("to"):
            q = q.filter(AuditLog.occurred_at <= datetime.fromisoformat(params["to"]))

        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        total = q.count()
        items = q.order_by(AuditLog.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "page": page, "page_size": page_size, "items": [e.to_dict() for e in items]}

    @staticmethod
    def append(action_type: str, actor_id, target_type: str, target_id: str,
               before=None, after=None, correlation_id: str = "") -> AuditLog:
        import json
        entry = AuditLog(
            action_type=action_type,
            actor_id=actor_id,
            target_type=target_type,
            target_id=str(target_id),
            before_state=json.dumps(before) if before else None,
            after_state=json.dumps(after) if after else None,
            correlation_id=correlation_id,
        )
        db.session.add(entry)
        return entry
