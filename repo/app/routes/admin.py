from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.audit_service import AuditService
from app.services.admin_service import AdminService

admin_bp = Blueprint("admin", __name__)

_TICKET_ROLES = ("Administrator", "Operations Manager", "Moderator")


@admin_bp.get("/audit-log")
@require_auth
@require_roles("Administrator")
def get_audit_log():
    params = {
        "action_type": request.args.get("action_type"),
        "user_id": request.args.get("user_id"),
        "from": request.args.get("from"),
        "to": request.args.get("to"),
        "page": int(request.args.get("page", 1)),
        "page_size": min(int(request.args.get("page_size", 20)), 100),
    }
    return jsonify(AuditService.query(params))


@admin_bp.post("/admin/tickets")
@require_auth
@require_roles(*_TICKET_ROLES)
def create_ticket():
    data = request.get_json(force=True) or {}
    ticket = AdminService.create_ticket(data, actor=g.current_user)
    return jsonify(ticket.to_dict()), 201


@admin_bp.get("/admin/tickets")
@require_auth
@require_roles(*_TICKET_ROLES)
def list_tickets():
    params = {
        "status": request.args.get("status"),
        "type": request.args.get("type"),
        "page": int(request.args.get("page", 1)),
        "page_size": min(int(request.args.get("page_size", 20)), 100),
    }
    return jsonify(AdminService.list_tickets(params, requester=g.current_user))


@admin_bp.patch("/admin/tickets/<ticket_id>")
@require_auth
@require_roles("Administrator", "Operations Manager")
def update_ticket(ticket_id):
    data = request.get_json(force=True) or {}
    ticket = AdminService.update_ticket(ticket_id, data, actor=g.current_user)
    return jsonify(ticket.to_dict())


@admin_bp.get("/admin/reports/group-leader-performance")
@require_auth
@require_roles("Administrator", "Operations Manager", "Group Leader")
def group_leader_performance():
    params = {
        "community_id": request.args.get("community_id"),
        "from": request.args.get("from"),
        "to": request.args.get("to"),
    }
    return jsonify(AdminService.group_leader_performance(params, requester=g.current_user))
