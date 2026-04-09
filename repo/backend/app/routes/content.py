from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.content_service import ContentService

content_bp = Blueprint("content", __name__)

_AUTHOR_ROLES = ("Administrator", "Operations Manager", "Moderator")
_PUBLISH_ROLES = ("Administrator", "Operations Manager")


@content_bp.post("/content")
@require_auth
@require_roles(*_AUTHOR_ROLES)
def create_content():
    data = request.get_json(force=True) or {}
    item = ContentService.create(data, author=g.current_user)
    return jsonify(item), 201


@content_bp.get("/content/<content_id>")
@require_auth
def get_content(content_id):
    version = request.args.get("version", type=int)
    return jsonify(ContentService.get(content_id, version=version, user=g.current_user))


@content_bp.patch("/content/<content_id>")
@require_auth
@require_roles(*_AUTHOR_ROLES)
def update_content(content_id):
    data = request.get_json(force=True) or {}
    return jsonify(ContentService.update(content_id, data, author=g.current_user))


@content_bp.post("/content/<content_id>/publish")
@require_auth
@require_roles(*_PUBLISH_ROLES)
def publish_content(content_id):
    return jsonify(ContentService.publish(content_id, actor=g.current_user))


@content_bp.post("/content/<content_id>/rollback")
@require_auth
@require_roles(*_PUBLISH_ROLES)
def rollback_content(content_id):
    data = request.get_json(force=True) or {}
    return jsonify(ContentService.rollback(content_id, data["target_version"], actor=g.current_user))


@content_bp.get("/content/<content_id>/versions")
@require_auth
@require_roles(*_AUTHOR_ROLES)
def list_versions(content_id):
    return jsonify(ContentService.list_versions(content_id))


@content_bp.post("/content/<content_id>/attachments")
@require_auth
@require_roles(*_AUTHOR_ROLES)
def upload_attachment(content_id):
    file = request.files.get("file")
    attachment = ContentService.add_attachment(content_id, file, actor=g.current_user)
    return jsonify(attachment.to_dict()), 201


@content_bp.get("/content/<content_id>/attachments")
@require_auth
def list_attachments(content_id):
    return jsonify(ContentService.list_attachments(content_id))


@content_bp.delete("/content/<content_id>/attachments/<attachment_id>")
@require_auth
@require_roles(*_PUBLISH_ROLES)
def delete_attachment(content_id, attachment_id):
    ContentService.delete_attachment(content_id, attachment_id)
    return "", 204
