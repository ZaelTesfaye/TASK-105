"""
RBAC decorator — checks the current_user's role against an allowed-roles list.
Must be applied after @require_auth.

Usage:
    @require_auth
    @require_roles("Administrator", "Operations Manager")
    def my_view(): ...
"""
from functools import wraps
from flask import g
from app.errors import ForbiddenError

ROLE_HIERARCHY = {
    "Administrator": 6,
    "Operations Manager": 5,
    "Moderator": 4,
    "Group Leader": 3,
    "Staff": 2,
    "Member": 1,
}


def require_roles(*roles: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = g.get("current_user")
            if user is None or user.role not in roles:
                raise ForbiddenError("forbidden", "Insufficient permissions")
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_min_role(min_role: str):
    """Allow any role with hierarchy level >= min_role."""
    min_level = ROLE_HIERARCHY.get(min_role, 0)

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = g.get("current_user")
            if user is None:
                raise ForbiddenError("forbidden", "Insufficient permissions")
            if ROLE_HIERARCHY.get(user.role, 0) < min_level:
                raise ForbiddenError("forbidden", "Insufficient permissions")
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_community_scope(user) -> str | None:
    """
    Row-level scope helper for community-scoped operations.

    Returns the community_id string if the user is a Group Leader (restricted
    to their one active community binding). Returns None for roles that have
    cross-community visibility (Administrator, Operations Manager, Moderator,
    Staff). Member-level scoping is enforced individually per service method.

    Raises ForbiddenError if a Group Leader has no active community binding.
    """
    if user.role != "Group Leader":
        return None
    from app.models.community import GroupLeaderBinding
    binding = GroupLeaderBinding.query.filter_by(
        user_id=user.user_id, active=True
    ).first()
    if binding is None:
        raise ForbiddenError("no_community_binding", "No active community assignment for this Group Leader")
    return str(binding.community_id)


def assert_self_or_elevated(
    requester, target_user_id: str,
    elevated_roles=("Administrator", "Operations Manager"),
) -> None:
    """
    Raise ForbiddenError unless the requester is the target user or has an elevated role.
    Used to enforce Member/Group Leader row-level scoping on user-owned resources.
    """
    if requester.role not in elevated_roles and str(requester.user_id) != str(target_user_id):
        raise ForbiddenError("forbidden", "Access restricted to own resources")
