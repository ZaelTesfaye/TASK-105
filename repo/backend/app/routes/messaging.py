"""
REST fallback endpoints for messaging.
WebSocket/STOMP handler is in app/websocket.py.
"""
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.messaging_service import MessagingService

messaging_bp = Blueprint("messaging", __name__)


@messaging_bp.post("/messages")
@require_auth
def send_message():
    data = request.get_json(force=True) or {}
    msg = MessagingService.send_message(data, sender=g.current_user)
    return jsonify(msg.to_dict()), 201


@messaging_bp.get("/messages")
@require_auth
def get_queued_messages():
    return jsonify(MessagingService.get_queued(g.current_user))


@messaging_bp.post("/messages/<message_id>/receipt")
@require_auth
def update_receipt(message_id):
    data = request.get_json(force=True) or {}
    result = MessagingService.update_receipt(message_id, data["status"], user=g.current_user)
    return jsonify(result)
