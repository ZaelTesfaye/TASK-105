from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.community_service import CommunityService
from app.schemas.community_schemas import (
    CreateCommunitySchema, UpdateCommunitySchema,
    CreateServiceAreaSchema, UpdateServiceAreaSchema,
)

communities_bp = Blueprint("communities", __name__)


@communities_bp.post("/communities")
@require_auth
@require_roles("Administrator", "Operations Manager")
def create_community():
    data = CreateCommunitySchema().load(request.get_json(force=True) or {})
    community = CommunityService.create(data)
    return jsonify(community.to_dict()), 201


@communities_bp.get("/communities")
@require_auth
def list_communities():
    filters = {k: request.args.get(k) for k in ("city", "state")}
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 20)), 100)
    return jsonify(CommunityService.list_communities(filters=filters, page=page, page_size=page_size))


@communities_bp.get("/communities/<community_id>")
@require_auth
def get_community(community_id):
    return jsonify(CommunityService.get_detail(community_id))


@communities_bp.patch("/communities/<community_id>")
@require_auth
@require_roles("Administrator", "Operations Manager")
def update_community(community_id):
    data = UpdateCommunitySchema().load(request.get_json(force=True) or {})
    community = CommunityService.update(community_id, data)
    return jsonify(community.to_dict())


@communities_bp.delete("/communities/<community_id>")
@require_auth
@require_roles("Administrator")
def delete_community(community_id):
    CommunityService.delete(community_id)
    return "", 204


# --- Service areas ---

@communities_bp.post("/communities/<community_id>/service-areas")
@require_auth
@require_roles("Administrator", "Operations Manager")
def create_service_area(community_id):
    data = CreateServiceAreaSchema().load(request.get_json(force=True) or {})
    area = CommunityService.create_service_area(community_id, data)
    return jsonify(area.to_dict()), 201


@communities_bp.get("/communities/<community_id>/service-areas")
@require_auth
def list_service_areas(community_id):
    return jsonify(CommunityService.list_service_areas(community_id))


@communities_bp.patch("/communities/<community_id>/service-areas/<area_id>")
@require_auth
@require_roles("Administrator", "Operations Manager")
def update_service_area(community_id, area_id):
    data = UpdateServiceAreaSchema().load(request.get_json(force=True) or {})
    area = CommunityService.update_service_area(community_id, area_id, data)
    return jsonify(area.to_dict())


@communities_bp.delete("/communities/<community_id>/service-areas/<area_id>")
@require_auth
@require_roles("Administrator")
def delete_service_area(community_id, area_id):
    CommunityService.delete_service_area(community_id, area_id)
    return "", 204


# --- Group leader bindings ---

@communities_bp.post("/communities/<community_id>/leader-binding")
@require_auth
@require_roles("Administrator")
def bind_leader(community_id):
    data = request.get_json(force=True) or {}
    binding = CommunityService.bind_leader(community_id, data["user_id"])
    return jsonify(binding.to_dict()), 201


@communities_bp.delete("/communities/<community_id>/leader-binding")
@require_auth
@require_roles("Administrator")
def unbind_leader(community_id):
    CommunityService.unbind_leader(community_id)
    return "", 204


@communities_bp.get("/communities/<community_id>/leader-binding/history")
@require_auth
@require_roles("Administrator", "Operations Manager")
def binding_history(community_id):
    return jsonify(CommunityService.binding_history(community_id))


# --- Community membership ---

@communities_bp.post("/communities/<community_id>/members")
@require_auth
def join_community(community_id):
    """Join a community (any authenticated user may join themselves)."""
    membership = CommunityService.join_community(community_id, g.current_user)
    return jsonify(membership.to_dict()), 201


@communities_bp.delete("/communities/<community_id>/members")
@require_auth
def leave_community(community_id):
    """Leave a community."""
    CommunityService.leave_community(community_id, g.current_user)
    return "", 204


@communities_bp.get("/communities/<community_id>/members")
@require_auth
@require_roles("Administrator", "Operations Manager", "Moderator")
def list_members(community_id):
    return jsonify(CommunityService.list_members(community_id))
