from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.template_service import TemplateService
from app.schemas.template_schemas import CreateTemplateSchema, UpdateTemplateSchema, TemplateFieldSchema

templates_bp = Blueprint("templates", __name__)

_MANAGE_ROLES = ("Administrator", "Operations Manager")


@templates_bp.post("/templates")
@require_auth
@require_roles(*_MANAGE_ROLES)
def create_template():
    data = CreateTemplateSchema().load(request.get_json(force=True) or {})
    # Remap validated fields back to the key the service expects
    if "fields_" in data:
        data["fields"] = data.pop("fields_")
    tmpl = TemplateService.create(data, author=g.current_user)
    return jsonify(tmpl), 201


@templates_bp.get("/templates/<template_id>")
@require_auth
def get_template(template_id):
    version = request.args.get("version", type=int)
    return jsonify(TemplateService.get(template_id, version=version, user=g.current_user))


@templates_bp.patch("/templates/<template_id>")
@require_auth
@require_roles(*_MANAGE_ROLES)
def update_template(template_id):
    data = UpdateTemplateSchema().load(request.get_json(force=True) or {})
    if "fields_" in data:
        data["fields"] = data.pop("fields_")
    return jsonify(TemplateService.update(template_id, data, author=g.current_user))


@templates_bp.post("/templates/<template_id>/publish")
@require_auth
@require_roles(*_MANAGE_ROLES)
def publish_template(template_id):
    return jsonify(TemplateService.publish(template_id, actor=g.current_user))


@templates_bp.post("/templates/<template_id>/rollback")
@require_auth
@require_roles(*_MANAGE_ROLES)
def rollback_template(template_id):
    data = request.get_json(force=True) or {}
    return jsonify(TemplateService.rollback(template_id, data["target_version"], actor=g.current_user))


@templates_bp.get("/templates/<template_id>/versions")
@require_auth
@require_roles(*_MANAGE_ROLES)
def list_versions(template_id):
    return jsonify(TemplateService.list_versions(template_id))


@templates_bp.post("/templates/<template_id>/migrations")
@require_auth
@require_roles("Administrator")
def create_migration(template_id):
    data = request.get_json(force=True) or {}
    # Validate field_mappings entries if the incoming version has fields
    if "fields" in data:
        TemplateFieldSchema(many=True).load(data["fields"])
    migration = TemplateService.create_migration(template_id, data)
    return jsonify(migration.to_dict()), 201


# --- Attachments ---

@templates_bp.post("/templates/<template_id>/attachments")
@require_auth
@require_roles(*_MANAGE_ROLES)
def upload_template_attachment(template_id):
    file = request.files.get("file")
    attachment = TemplateService.add_attachment(template_id, file, actor=g.current_user)
    return jsonify(attachment.to_dict()), 201


@templates_bp.get("/templates/<template_id>/attachments")
@require_auth
def list_template_attachments(template_id):
    return jsonify(TemplateService.list_attachments(template_id))


@templates_bp.delete("/templates/<template_id>/attachments/<attachment_id>")
@require_auth
@require_roles(*_MANAGE_ROLES)
def delete_template_attachment(template_id, attachment_id):
    TemplateService.delete_attachment(template_id, attachment_id)
    return "", 204
