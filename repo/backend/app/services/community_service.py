"""Community, ServiceArea, and GroupLeaderBinding service."""
import json
import re
from datetime import datetime, timezone

from app.extensions import db
from app.models.community import Community, ServiceArea, GroupLeaderBinding, CommunityMember
from app.models.user import User
from app.errors import NotFoundError, AppError, UnprocessableError

_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")


class CommunityService:

    @staticmethod
    def _get_or_404(community_id: str) -> Community:
        c = db.session.get(Community, community_id)
        if c is None or c.deleted_at is not None:
            raise NotFoundError("community")
        return c

    @staticmethod
    def create(data: dict) -> Community:
        if not _ZIP_RE.match(data.get("zip", "")):
            raise AppError("invalid_zip", "zip must be a 5 or 9-digit US ZIP", field="zip", status_code=400)
        c = Community(
            name=data["name"],
            address_line1=data["address_line1"],
            address_line2=data.get("address_line2"),
            city=data["city"],
            state=data["state"],
            zip=data["zip"],
            service_hours=json.dumps(data.get("service_hours", {})),
            fulfillment_scope=data.get("fulfillment_scope", ""),
        )
        db.session.add(c)
        db.session.commit()
        return c

    @staticmethod
    def list_communities(filters: dict, page: int, page_size: int) -> dict:
        q = Community.query.filter(Community.deleted_at.is_(None))
        if filters.get("city"):
            q = q.filter(Community.city.ilike(f"%{filters['city']}%"))
        if filters.get("state"):
            q = q.filter(Community.state == filters["state"].upper())
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "page": page, "page_size": page_size, "items": [c.to_dict() for c in items]}

    @staticmethod
    def get_detail(community_id: str) -> dict:
        c = CommunityService._get_or_404(community_id)
        result = c.to_dict()
        active_binding = GroupLeaderBinding.query.filter_by(community_id=c.community_id, active=True).first()
        if active_binding:
            leader = db.session.get(User, active_binding.user_id)
            result["active_group_leader"] = (
                {"user_id": str(leader.user_id), "username": leader.username} if leader else None
            )
        else:
            result["active_group_leader"] = None
        return result

    @staticmethod
    def update(community_id: str, data: dict) -> Community:
        c = CommunityService._get_or_404(community_id)
        if "zip" in data and not _ZIP_RE.match(data["zip"]):
            raise AppError("invalid_zip", "zip must be a 5 or 9-digit US ZIP", field="zip", status_code=400)
        for field in ("name", "address_line1", "address_line2", "city", "state", "zip", "fulfillment_scope"):
            if field in data:
                setattr(c, field, data[field])
        if "service_hours" in data:
            c.service_hours = json.dumps(data["service_hours"])
        db.session.commit()
        return c

    @staticmethod
    def delete(community_id: str) -> None:
        c = CommunityService._get_or_404(community_id)
        c.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    # --- Service Areas ---

    @staticmethod
    def create_service_area(community_id: str, data: dict) -> ServiceArea:
        CommunityService._get_or_404(community_id)
        if not _ZIP_RE.match(data.get("zip", "")):
            raise AppError("invalid_zip", "zip must be a 5 or 9-digit US ZIP", field="zip", status_code=400)
        area = ServiceArea(
            community_id=community_id,
            name=data["name"],
            address_line1=data["address_line1"],
            city=data["city"],
            state=data["state"],
            zip=data["zip"],
            notes=data.get("notes"),
        )
        db.session.add(area)
        db.session.commit()
        return area

    @staticmethod
    def list_service_areas(community_id: str) -> list:
        CommunityService._get_or_404(community_id)
        areas = ServiceArea.query.filter_by(community_id=community_id, deleted_at=None).all()
        return [a.to_dict() for a in areas]

    @staticmethod
    def update_service_area(community_id: str, area_id: str, data: dict) -> ServiceArea:
        area = db.session.get(ServiceArea, area_id)
        if area is None or str(area.community_id) != community_id or area.deleted_at is not None:
            raise NotFoundError("service_area")
        if "zip" in data and not _ZIP_RE.match(data["zip"]):
            raise AppError("invalid_zip", "zip must be a 5 or 9-digit US ZIP", field="zip", status_code=400)
        for field in ("name", "address_line1", "city", "state", "zip", "notes"):
            if field in data:
                setattr(area, field, data[field])
        db.session.commit()
        return area

    @staticmethod
    def delete_service_area(community_id: str, area_id: str) -> None:
        area = db.session.get(ServiceArea, area_id)
        if area is None or str(area.community_id) != community_id:
            raise NotFoundError("service_area")
        area.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    # --- Group Leader Bindings ---

    @staticmethod
    def bind_leader(community_id: str, user_id: str) -> GroupLeaderBinding:
        CommunityService._get_or_404(community_id)
        user = db.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFoundError("user")
        if user.role != "Group Leader":
            raise UnprocessableError("user_not_group_leader", "User must have role Group Leader")

        # Atomic swap inside a transaction
        existing = GroupLeaderBinding.query.filter_by(community_id=community_id, active=True).first()
        if existing:
            existing.active = False
            existing.unbound_at = datetime.now(timezone.utc)

        binding = GroupLeaderBinding(community_id=community_id, user_id=user_id, active=True)
        db.session.add(binding)
        db.session.commit()
        return binding

    @staticmethod
    def unbind_leader(community_id: str) -> None:
        binding = GroupLeaderBinding.query.filter_by(community_id=community_id, active=True).first()
        if binding:
            binding.active = False
            binding.unbound_at = datetime.now(timezone.utc)
            db.session.commit()

    @staticmethod
    def binding_history(community_id: str) -> list:
        bindings = (GroupLeaderBinding.query.filter_by(community_id=community_id)
                    .order_by(GroupLeaderBinding.bound_at.desc()).all())
        return [b.to_dict() for b in bindings]

    # --- Membership ---

    @staticmethod
    def join_community(community_id: str, user) -> CommunityMember:
        CommunityService._get_or_404(community_id)
        existing = CommunityMember.query.filter_by(
            community_id=community_id, user_id=user.user_id
        ).first()
        if existing is not None:
            if existing.left_at is not None:
                # Re-join: clear the left_at timestamp
                existing.left_at = None
                db.session.commit()
                return existing
            raise AppError("already_member", "User is already a member of this community",
                           status_code=409)
        membership = CommunityMember(community_id=community_id, user_id=user.user_id)
        db.session.add(membership)
        db.session.commit()
        return membership

    @staticmethod
    def leave_community(community_id: str, user) -> None:
        membership = CommunityMember.query.filter_by(
            community_id=community_id, user_id=user.user_id, left_at=None
        ).first()
        if membership is None:
            raise NotFoundError("community_membership")
        membership.left_at = datetime.now(timezone.utc)
        db.session.commit()

    @staticmethod
    def list_members(community_id: str) -> list:
        CommunityService._get_or_404(community_id)
        members = CommunityMember.query.filter_by(
            community_id=community_id, left_at=None
        ).all()
        return [m.to_dict() for m in members]

    @staticmethod
    def get_active_member_ids(community_id: str) -> list:
        members = CommunityMember.query.filter_by(
            community_id=community_id, left_at=None
        ).all()
        return [str(m.user_id) for m in members]
