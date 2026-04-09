from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.user_service import UserService

users_bp = Blueprint("users", __name__)


@users_bp.get("/users")
@require_auth
@require_roles("Administrator", "Operations Manager")
def list_users():
    role = request.args.get("role")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 20)), 100)
    include_deleted = request.args.get("include_deleted") == "true" and g.current_user.role == "Administrator"
    return jsonify(UserService.list_users(role=role, page=page, page_size=page_size, include_deleted=include_deleted))


@users_bp.get("/users/<user_id>")
@require_auth
def get_user(user_id):
    user = UserService.get_user(user_id, requester=g.current_user)
    return jsonify(user.to_dict())


@users_bp.patch("/users/<user_id>")
@require_auth
def update_user(user_id):
    data = request.get_json(force=True) or {}
    user = UserService.update_user(user_id, data, requester=g.current_user)
    return jsonify(user.to_dict())


@users_bp.patch("/users/<user_id>/password")
@require_auth
def change_password(user_id):
    data = request.get_json(force=True) or {}
    UserService.change_password(user_id, data, requester=g.current_user)
    return "", 204


@users_bp.delete("/users/<user_id>")
@require_auth
@require_roles("Administrator")
def delete_user(user_id):
    UserService.delete_user(user_id)
    return "", 204
