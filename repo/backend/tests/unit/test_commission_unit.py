"""
Unit tests for CommissionService — direct service calls, no HTTP.

Covered:
  - create_rule happy path
  - create_rule invalid rate ranges (floor > rate, ceiling < rate, ceiling > 15)
  - create_rule invalid settlement cycle
  - update_rule validates BEFORE mutating the model
  - resolve_rate precedence: category > community default > system default (6%)
  - create_settlement idempotency (same key returns same settlement, created=False)
  - finalize blocked when open dispute exists
"""
import uuid

import pytest

from app.services.commission_service import CommissionService
from app.models.community import Community
from app.models.commission import CommissionRule, SettlementRun, SettlementDispute
from app.errors import AppError, UnprocessableError
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _suffix():
    return uuid.uuid4().hex[:8]


def _make_community():
    """Insert a minimal Community row and return it (caller must be inside app_context)."""
    c = Community(
        name=f"Comm-{_suffix()}",
        address_line1="123 Test St",
        city="Testville",
        state="TX",
        zip="12345",
    )
    db.session.add(c)
    db.session.flush()
    return c


def _make_actor(app):
    from app.services.auth_service import AuthService
    return AuthService.register(f"comm_actor_{_suffix()}", "CommActorPass1!")


# ---------------------------------------------------------------------------
# create_rule
# ---------------------------------------------------------------------------

class TestCreateRule:

    def test_create_rule_valid(self, app):
        """Creates a rule with floor=2, rate=6, ceiling=12 without raising."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            rule = CommissionService.create_rule(str(comm.community_id), {
                "floor": 2,
                "rate": 6,
                "ceiling": 12,
                "settlement_cycle": "weekly",
            })
            assert rule.rule_id is not None
            assert rule.floor == 2.0
            assert rule.rate == 6.0
            assert rule.ceiling == 12.0

    def test_create_rule_floor_gt_rate(self, app):
        """floor=8 > rate=6 raises AppError(error='invalid_rate_range')."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            with pytest.raises(AppError) as exc_info:
                CommissionService.create_rule(str(comm.community_id), {
                    "floor": 8,
                    "rate": 6,
                    "ceiling": 12,
                })
            assert exc_info.value.error == "invalid_rate_range"

    def test_create_rule_ceiling_lt_rate(self, app):
        """ceiling=8 < rate=10 raises AppError(error='invalid_rate_range')."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            with pytest.raises(AppError) as exc_info:
                CommissionService.create_rule(str(comm.community_id), {
                    "floor": 0,
                    "rate": 10,
                    "ceiling": 8,
                })
            assert exc_info.value.error == "invalid_rate_range"

    def test_create_rule_ceiling_above_15(self, app):
        """ceiling=16 raises AppError(error='invalid_rate_range')."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            with pytest.raises(AppError) as exc_info:
                CommissionService.create_rule(str(comm.community_id), {
                    "floor": 0,
                    "rate": 10,
                    "ceiling": 16,
                })
            assert exc_info.value.error == "invalid_rate_range"

    def test_create_rule_invalid_cycle(self, app):
        """settlement_cycle='monthly' raises AppError(error='invalid_cycle')."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            with pytest.raises(AppError) as exc_info:
                CommissionService.create_rule(str(comm.community_id), {
                    "floor": 0,
                    "rate": 6,
                    "ceiling": 12,
                    "settlement_cycle": "monthly",
                })
            assert exc_info.value.error == "invalid_cycle"


# ---------------------------------------------------------------------------
# update_rule
# ---------------------------------------------------------------------------

class TestUpdateRule:

    def test_update_rule_prevalidates(self, app):
        """
        Updating floor=9 on a rule that has rate=6 must raise before touching
        the model — rule.floor must NOT be mutated to 9.
        """
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            rule = CommissionService.create_rule(str(comm.community_id), {
                "floor": 0,
                "rate": 6,
                "ceiling": 12,
            })
            original_floor = rule.floor

            with pytest.raises(AppError) as exc_info:
                CommissionService.update_rule(str(comm.community_id), str(rule.rule_id), {
                    "floor": 9,   # invalid: 9 > rate 6
                })
            assert exc_info.value.error == "invalid_rate_range"

            # Reload from DB to verify no mutation occurred
            db.session.expire(rule)
            refreshed = db.session.get(CommissionRule, rule.rule_id)
            assert refreshed.floor == original_floor


# ---------------------------------------------------------------------------
# resolve_rate
# ---------------------------------------------------------------------------

class TestResolveRate:

    def test_resolve_rate_category_wins(self, app):
        """Category-specific rule (8%) beats community default (6%)."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            # Community default
            CommissionService.create_rule(str(comm.community_id), {
                "rate": 6, "floor": 0, "ceiling": 15,
            })
            # Category-specific rule
            CommissionService.create_rule(str(comm.community_id), {
                "rate": 8, "floor": 0, "ceiling": 15,
                "product_category": "Electronics",
            })

            rate = CommissionService.resolve_rate(str(comm.community_id), "Electronics")
            assert rate == 8.0

    def test_resolve_rate_community_default(self, app):
        """Community default (7%) is used when no category-specific rule exists."""
        with app.app_context():
            comm = _make_community()
            db.session.commit()

            CommissionService.create_rule(str(comm.community_id), {
                "rate": 7, "floor": 0, "ceiling": 15,
            })

            rate = CommissionService.resolve_rate(str(comm.community_id), "NonExistentCat")
            assert rate == 7.0

    def test_resolve_rate_system_default_6(self, app):
        """Returns 6.0 when no rules exist for the community at all."""
        with app.app_context():
            # Fresh community with no rules
            comm = _make_community()
            db.session.commit()

            rate = CommissionService.resolve_rate(str(comm.community_id))
            assert rate == 6.0


# ---------------------------------------------------------------------------
# Settlements — idempotency
# ---------------------------------------------------------------------------

class TestSettlementIdempotency:

    def test_settlement_idempotent(self, app):
        """
        Calling create_settlement twice with the same idempotency_key returns the
        same settlement_id and created=False on the second call.
        """
        with app.app_context():
            actor = _make_actor(app)
            comm = _make_community()
            db.session.commit()

            idem_key = f"idem-{_suffix()}"
            data = {
                "community_id": str(comm.community_id),
                "idempotency_key": idem_key,
                "period_start": "2024-01-01",
                "period_end": "2024-01-07",
            }

            s1, created1 = CommissionService.create_settlement(data, actor)
            assert created1 is True

            s2, created2 = CommissionService.create_settlement(data, actor)
            assert created2 is False
            assert str(s1.settlement_id) == str(s2.settlement_id)


# ---------------------------------------------------------------------------
# Finalize — blocked by open dispute
# ---------------------------------------------------------------------------

class TestFinalizeSettlement:

    def test_finalize_blocked_by_open_dispute(self, app):
        """finalize raises UnprocessableError when there is at least one open dispute."""
        with app.app_context():
            actor = _make_actor(app)
            comm = _make_community()
            db.session.commit()

            settlement, _ = CommissionService.create_settlement({
                "community_id": str(comm.community_id),
                "idempotency_key": f"fin-{_suffix()}",
                "period_start": "2024-01-01",
                "period_end": "2024-01-07",
            }, actor)

            # Directly insert an open dispute (bypass the dispute window check)
            dispute = SettlementDispute(
                settlement_id=settlement.settlement_id,
                filed_by=actor.user_id,
                reason="Test dispute",
                disputed_amount=50.0,
                status="open",
            )
            db.session.add(dispute)
            db.session.commit()

            with pytest.raises(UnprocessableError) as exc_info:
                CommissionService.finalize(str(settlement.settlement_id), actor)
            assert exc_info.value.error == "settlement_blocked_by_open_dispute"
