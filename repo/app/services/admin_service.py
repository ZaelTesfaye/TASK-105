"""Admin ticket and reporting service."""
from datetime import datetime, timezone, date

from app.extensions import db
from app.models.admin import AdminTicket
from app.models.user import User
from app.errors import NotFoundError, ForbiddenError
from app.services.audit_service import AuditService
from flask import g
from sqlalchemy import func, false


def _cid() -> str:
    return getattr(g, "correlation_id", "n/a")


class AdminService:

    @staticmethod
    def create_ticket(data: dict, actor: User) -> AdminTicket:
        ticket = AdminTicket(
            type=data["type"],
            subject=data["subject"],
            body=data["body"],
            target_type=data.get("target_type"),
            target_id=data.get("target_id"),
            created_by=actor.user_id,
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket

    @staticmethod
    def list_tickets(params: dict, requester: User) -> dict:
        q = AdminTicket.query
        if requester.role == "Moderator":
            q = q.filter(AdminTicket.created_by == requester.user_id)
        if params.get("status"):
            q = q.filter(AdminTicket.status == params["status"])
        if params.get("type"):
            q = q.filter(AdminTicket.type == params["type"])
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        total = q.count()
        items = q.order_by(AdminTicket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "page": page, "page_size": page_size, "items": [t.to_dict() for t in items]}

    @staticmethod
    def update_ticket(ticket_id: str, data: dict, actor: User) -> AdminTicket:
        ticket = db.session.get(AdminTicket, ticket_id)
        if ticket is None:
            raise NotFoundError("admin_ticket")
        if "status" in data:
            ticket.status = data["status"]
            if data["status"] == "closed":
                ticket.resolved_at = datetime.now(timezone.utc)
        if "resolution_notes" in data:
            ticket.resolution_notes = data["resolution_notes"]
        AuditService.append(
            action_type="moderation", actor_id=actor.user_id,
            target_type="admin_ticket", target_id=str(ticket_id),
            after={"status": ticket.status},
            correlation_id=_cid(),
        )
        db.session.commit()
        return ticket

    @staticmethod
    def group_leader_performance(params: dict, requester: User) -> dict:
        """
        Returns aggregated performance metrics for the given period and community.
        Row-level scoping: Group Leaders may only query their bound community.
        Totals are derived from SettlementRun records; top products from inventory issues.
        """
        from app.models.commission import SettlementRun
        from app.models.inventory import InventoryTransaction
        from app.models.catalog import Product

        community_id = params.get("community_id")
        from_str = params.get("from")
        to_str = params.get("to")

        if requester.role == "Group Leader":
            from app.models.community import GroupLeaderBinding
            binding = GroupLeaderBinding.query.filter_by(
                user_id=requester.user_id, active=True,
            ).first()
            if binding is None or (community_id and str(binding.community_id) != community_id):
                raise ForbiddenError("forbidden", "Access restricted to your bound community")
            community_id = str(binding.community_id)

        # Aggregate from settlement runs
        q = SettlementRun.query
        if community_id:
            q = q.filter(SettlementRun.community_id == community_id)
        if from_str:
            try:
                q = q.filter(SettlementRun.period_start >= date.fromisoformat(from_str))
            except (ValueError, TypeError):
                pass
        if to_str:
            try:
                q = q.filter(SettlementRun.period_end <= date.fromisoformat(to_str))
            except (ValueError, TypeError):
                pass
        runs = q.all()
        total_order_value = sum(r.total_order_value for r in runs)
        commission_earned = sum(r.commission_amount for r in runs)
        settlement_run_count = len(runs)

        from app.models.inventory import Warehouse

        wh_ids = None
        if community_id:
            wh_ids = [
                w.warehouse_id
                for w in Warehouse.query.filter_by(community_id=community_id).all()
            ]

        def _apply_issue_filters(base_q):
            qn = base_q.filter(InventoryTransaction.type == "issue")
            if community_id:
                if wh_ids:
                    qn = qn.filter(InventoryTransaction.warehouse_id.in_(wh_ids))
                else:
                    qn = qn.filter(false())
            if from_str:
                try:
                    d = date.fromisoformat(from_str)
                    qn = qn.filter(
                        InventoryTransaction.occurred_at >= datetime(d.year, d.month, d.day)
                    )
                except (ValueError, TypeError):
                    pass
            if to_str:
                try:
                    d = date.fromisoformat(to_str)
                    qn = qn.filter(
                        InventoryTransaction.occurred_at
                        <= datetime(d.year, d.month, d.day, 23, 59, 59)
                    )
                except (ValueError, TypeError):
                    pass
            return qn

        total_orders = (
            _apply_issue_filters(db.session.query(InventoryTransaction))
            .with_entities(func.count(InventoryTransaction.transaction_id))
            .scalar()
            or 0
        )

        txn_q = _apply_issue_filters(
            db.session.query(
                InventoryTransaction.sku_id,
                func.sum(func.abs(InventoryTransaction.quantity_delta)).label("qty"),
            )
        )
        top_rows = (
            txn_q.group_by(InventoryTransaction.sku_id)
            .order_by(func.sum(func.abs(InventoryTransaction.quantity_delta)).desc())
            .limit(5)
            .all()
        )
        top_products = []
        for sku_id, qty in top_rows:
            product = db.session.get(Product, sku_id)
            if product:
                top_products.append({
                    "sku_id": str(sku_id),
                    "name": product.name,
                    "quantity_issued": int(qty),
                })

        return {
            "community_id": community_id,
            "period": {"from": from_str, "to": to_str},
            "total_orders": total_orders,
            "settlement_run_count": settlement_run_count,
            "total_order_value_usd": total_order_value,
            "commission_earned_usd": commission_earned,
            "top_products": top_products,
        }
