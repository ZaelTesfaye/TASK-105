"""
Unit tests for AdminService — all calls go directly to the service layer, no HTTP.

Covered:
  - Ticket creation with required fields
  - Ticket status transitions (valid and invalid)
  - Group leader performance report computation logic
"""
import uuid

import pytest

from app.services.auth_service import AuthService
from app.services.admin_service import AdminService
from app.models.admin import TICKET_STATUSES
from app.errors import NotFoundError, ForbiddenError
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _u(prefix="adm"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _pw():
    return "ValidPass1234!"


def _ticket_payload(**overrides):
    base = {
        "type": "moderation",
        "subject": "Test ticket subject",
        "body": "Test ticket body text",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Ticket creation
# ---------------------------------------------------------------------------

class TestCreateTicket:

    def test_create_ticket_with_required_fields(self, app):
        """AdminService.create_ticket returns an AdminTicket with matching fields."""
        with app.app_context():
            actor = AuthService.register(_u(), _pw(), role="Administrator")
            ticket = AdminService.create_ticket(_ticket_payload(), actor)
            assert ticket.ticket_id is not None
            assert ticket.type == "moderation"
            assert ticket.subject == "Test ticket subject"
            assert ticket.body == "Test ticket body text"
            assert ticket.status == "open"

    def test_create_ticket_with_target(self, app):
        """Ticket can optionally include target_type and target_id."""
        with app.app_context():
            actor = AuthService.register(_u(), _pw(), role="Administrator")
            ticket = AdminService.create_ticket(
                _ticket_payload(target_type="User", target_id="some-user-id"),
                actor,
            )
            assert ticket.target_type == "User"
            assert ticket.target_id == "some-user-id"

    def test_create_ticket_all_types(self, app):
        """All defined ticket types can be created."""
        with app.app_context():
            actor = AuthService.register(_u(), _pw(), role="Administrator")
            for ticket_type in ("moderation", "report", "other"):
                ticket = AdminService.create_ticket(
                    _ticket_payload(type=ticket_type), actor
                )
                assert ticket.type == ticket_type


# ---------------------------------------------------------------------------
# Ticket status transitions
# ---------------------------------------------------------------------------

class TestTicketStatusTransition:

    def test_update_status_to_in_progress(self, app):
        """Transitioning ticket status to in_progress succeeds."""
        with app.app_context():
            actor = AuthService.register(_u(), _pw(), role="Administrator")
            ticket = AdminService.create_ticket(_ticket_payload(), actor)
            updated = AdminService.update_ticket(
                str(ticket.ticket_id), {"status": "in_progress"}, actor
            )
            assert updated.status == "in_progress"

    def test_update_status_to_closed_sets_resolved_at(self, app):
        """Closing a ticket sets resolved_at timestamp."""
        with app.app_context():
            actor = AuthService.register(_u(), _pw(), role="Administrator")
            ticket = AdminService.create_ticket(_ticket_payload(), actor)
            updated = AdminService.update_ticket(
                str(ticket.ticket_id), {"status": "closed", "resolution_notes": "Done"}, actor
            )
            assert updated.status == "closed"
            assert updated.resolved_at is not None
            assert updated.resolution_notes == "Done"

    def test_update_nonexistent_ticket_404(self, app):
        """Updating a non-existent ticket raises NotFoundError."""
        with app.app_context():
            actor = AuthService.register(_u(), _pw(), role="Administrator")
            with pytest.raises(NotFoundError):
                AdminService.update_ticket(uuid.uuid4().hex, {"status": "closed"}, actor)


# ---------------------------------------------------------------------------
# Group leader performance report
# ---------------------------------------------------------------------------

class TestGroupLeaderPerformance:

    def test_performance_report_returns_expected_structure(self, app):
        """group_leader_performance returns a dict with expected keys."""
        with app.app_context():
            admin = AuthService.register(_u(), _pw(), role="Administrator")
            report = AdminService.group_leader_performance(
                {"from": "2026-01-01", "to": "2026-12-31"}, admin
            )
            assert "total_orders" in report
            assert "settlement_run_count" in report
            assert "total_order_value_usd" in report
            assert "commission_earned_usd" in report
            assert "top_products" in report
            assert "period" in report

    def test_performance_report_gl_forbidden_without_binding(self, app):
        """A Group Leader with no active binding is rejected."""
        with app.app_context():
            gl = AuthService.register(_u(), _pw(), role="Group Leader")
            with pytest.raises(ForbiddenError):
                AdminService.group_leader_performance(
                    {"from": "2026-01-01", "to": "2026-12-31"}, gl
                )

    def test_performance_report_with_community_filter(self, app):
        """Passing community_id scopes the report to that community."""
        with app.app_context():
            admin = AuthService.register(_u(), _pw(), role="Administrator")
            report = AdminService.group_leader_performance(
                {"community_id": uuid.uuid4().hex, "from": "2026-01-01", "to": "2026-12-31"},
                admin,
            )
            assert report["settlement_run_count"] == 0
            assert report["total_order_value_usd"] == 0
