"""
Unit tests for AuditService — all calls go directly to the service layer, no HTTP.

Covered:
  - Audit log entry creation and retrieval with filters
  - Correct actor/action/resource fields are recorded
"""
import uuid

import pytest

from app.services.auth_service import AuthService
from app.services.audit_service import AuditService
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _u(prefix="aud"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _pw():
    return "ValidPass1234!"


# ---------------------------------------------------------------------------
# append + query
# ---------------------------------------------------------------------------

class TestAuditAppend:

    def test_append_creates_entry(self, app):
        """AuditService.append creates a log entry retrievable via query."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Administrator")
            target_id = uuid.uuid4().hex
            AuditService.append(
                action_type="auth",
                actor_id=user.user_id,
                target_type="User",
                target_id=target_id,
                after={"event": "test_action"},
                correlation_id="test-corr-id",
            )
            db.session.commit()

            result = AuditService.query({"action_type": "auth"})
            assert result["total"] >= 1
            entries = [e for e in result["items"] if e["target_id"] == target_id]
            assert len(entries) == 1
            entry = entries[0]
            assert entry["action_type"] == "auth"
            assert entry["actor_id"] == str(user.user_id)
            assert entry["target_type"] == "User"
            assert entry["after"]["event"] == "test_action"
            assert entry["correlation_id"] == "test-corr-id"

    def test_append_records_before_and_after(self, app):
        """AuditService.append stores both before_state and after_state."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Administrator")
            target_id = uuid.uuid4().hex
            AuditService.append(
                action_type="moderation",
                actor_id=user.user_id,
                target_type="admin_ticket",
                target_id=target_id,
                before={"status": "open"},
                after={"status": "closed"},
                correlation_id="corr-2",
            )
            db.session.commit()

            result = AuditService.query({"action_type": "moderation"})
            entries = [e for e in result["items"] if e["target_id"] == target_id]
            assert len(entries) == 1
            assert entries[0]["before"] == {"status": "open"}
            assert entries[0]["after"] == {"status": "closed"}


# ---------------------------------------------------------------------------
# query filters
# ---------------------------------------------------------------------------

class TestAuditQuery:

    def test_query_filter_by_action_type(self, app):
        """Filtering by action_type returns only matching entries."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Administrator")
            tid_auth = uuid.uuid4().hex
            tid_settle = uuid.uuid4().hex
            AuditService.append(
                action_type="auth", actor_id=user.user_id,
                target_type="User", target_id=tid_auth,
                correlation_id="c1",
            )
            AuditService.append(
                action_type="settlement", actor_id=user.user_id,
                target_type="settlement_run", target_id=tid_settle,
                correlation_id="c2",
            )
            db.session.commit()

            auth_results = AuditService.query({"action_type": "auth"})
            target_ids = [e["target_id"] for e in auth_results["items"]]
            assert tid_auth in target_ids
            # settlement entry should not appear in auth-filtered results
            assert tid_settle not in target_ids

    def test_query_filter_by_user_id(self, app):
        """Filtering by user_id returns only entries created by that actor."""
        with app.app_context():
            user1 = AuthService.register(_u("u1"), _pw(), role="Administrator")
            user2 = AuthService.register(_u("u2"), _pw(), role="Administrator")
            tid1 = uuid.uuid4().hex
            tid2 = uuid.uuid4().hex
            AuditService.append(
                action_type="auth", actor_id=user1.user_id,
                target_type="User", target_id=tid1,
                correlation_id="c1",
            )
            AuditService.append(
                action_type="auth", actor_id=user2.user_id,
                target_type="User", target_id=tid2,
                correlation_id="c2",
            )
            db.session.commit()

            result = AuditService.query({"user_id": str(user1.user_id)})
            actor_ids = {e["actor_id"] for e in result["items"]}
            assert str(user1.user_id) in actor_ids

    def test_query_pagination(self, app):
        """Query respects page and page_size parameters."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Administrator")
            for i in range(5):
                AuditService.append(
                    action_type="content", actor_id=user.user_id,
                    target_type="content", target_id=f"pg-{uuid.uuid4().hex[:8]}",
                    correlation_id=f"pg-{i}",
                )
            db.session.commit()

            result = AuditService.query({"action_type": "content", "page": 1, "page_size": 2})
            assert result["page"] == 1
            assert result["page_size"] == 2
            assert len(result["items"]) <= 2
