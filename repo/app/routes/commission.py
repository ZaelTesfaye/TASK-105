from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.commission_service import CommissionService

commission_bp = Blueprint("commission", __name__)


@commission_bp.post("/communities/<community_id>/commission-rules")
@require_auth
@require_roles("Administrator", "Operations Manager")
def create_rule(community_id):
    data = request.get_json(force=True) or {}
    rule = CommissionService.create_rule(community_id, data)
    return jsonify(rule.to_dict()), 201


@commission_bp.get("/communities/<community_id>/commission-rules")
@require_auth
def list_rules(community_id):
    # Group Leaders may only view rules for their own community
    CommissionService.assert_can_read(community_id, g.current_user)
    return jsonify(CommissionService.list_rules(community_id))


@commission_bp.patch("/communities/<community_id>/commission-rules/<rule_id>")
@require_auth
@require_roles("Administrator", "Operations Manager")
def update_rule(community_id, rule_id):
    data = request.get_json(force=True) or {}
    rule = CommissionService.update_rule(community_id, rule_id, data)
    return jsonify(rule.to_dict())


@commission_bp.delete("/communities/<community_id>/commission-rules/<rule_id>")
@require_auth
@require_roles("Administrator")
def delete_rule(community_id, rule_id):
    CommissionService.delete_rule(community_id, rule_id)
    return "", 204


# --- Settlements ---

@commission_bp.post("/settlements")
@require_auth
@require_roles("Administrator", "Operations Manager")
def create_settlement():
    data = request.get_json(force=True) or {}
    settlement, created = CommissionService.create_settlement(data, actor=g.current_user)
    # 201 on creation; 409 with existing settlement body on duplicate idempotency key
    return jsonify(settlement.to_dict()), 201 if created else 409


@commission_bp.get("/settlements/<settlement_id>")
@require_auth
def get_settlement(settlement_id):
    CommissionService.assert_can_read_settlement(settlement_id, g.current_user)
    settlement = CommissionService.get_settlement(settlement_id)
    return jsonify(settlement.to_dict())


@commission_bp.post("/settlements/<settlement_id>/disputes")
@require_auth
def file_dispute(settlement_id):
    data = request.get_json(force=True) or {}
    dispute = CommissionService.file_dispute(settlement_id, data, actor=g.current_user)
    return jsonify(dispute.to_dict()), 201


@commission_bp.patch("/settlements/<settlement_id>/disputes/<dispute_id>")
@require_auth
@require_roles("Administrator", "Operations Manager")
def resolve_dispute(settlement_id, dispute_id):
    data = request.get_json(force=True) or {}
    dispute = CommissionService.resolve_dispute(settlement_id, dispute_id, data, actor=g.current_user)
    return jsonify(dispute.to_dict())


@commission_bp.post("/settlements/<settlement_id>/finalize")
@require_auth
@require_roles("Administrator", "Operations Manager")
def finalize_settlement(settlement_id):
    settlement = CommissionService.finalize(settlement_id, actor=g.current_user)
    return jsonify(settlement.to_dict())
