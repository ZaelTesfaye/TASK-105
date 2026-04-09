from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid


class Community(db.Model):
    __tablename__ = "communities"

    community_id = db.Column(GUID, primary_key=True, default=new_uuid)
    name = db.Column(db.String(256), nullable=False)
    address_line1 = db.Column(db.String(256), nullable=False)
    address_line2 = db.Column(db.String(256), nullable=True)
    city = db.Column(db.String(128), nullable=False)
    state = db.Column(db.String(2), nullable=False)
    zip = db.Column(db.String(10), nullable=False)
    # JSON blob: {"monday": "09:00-17:00", ...}
    service_hours = db.Column(db.Text, nullable=False, default="{}")
    fulfillment_scope = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime, nullable=True)

    service_areas = db.relationship("ServiceArea", back_populates="community", lazy="dynamic")
    bindings = db.relationship("GroupLeaderBinding", back_populates="community", lazy="dynamic")

    def to_dict(self) -> dict:
        import json
        return {
            "community_id": str(self.community_id),
            "name": self.name,
            "address": {
                "line1": self.address_line1,
                "line2": self.address_line2,
                "city": self.city,
                "state": self.state,
                "zip": self.zip,
            },
            "service_hours": json.loads(self.service_hours),
            "fulfillment_scope": self.fulfillment_scope,
            "created_at": self.created_at.isoformat(),
        }


class ServiceArea(db.Model):
    __tablename__ = "service_areas"

    service_area_id = db.Column(GUID, primary_key=True, default=new_uuid)
    community_id = db.Column(GUID, db.ForeignKey("communities.community_id"), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    address_line1 = db.Column(db.String(256), nullable=False)
    city = db.Column(db.String(128), nullable=False)
    state = db.Column(db.String(2), nullable=False)
    zip = db.Column(db.String(10), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime, nullable=True)

    community = db.relationship("Community", back_populates="service_areas")

    def to_dict(self) -> dict:
        return {
            "service_area_id": str(self.service_area_id),
            "community_id": str(self.community_id),
            "name": self.name,
            "address_line1": self.address_line1,
            "city": self.city,
            "state": self.state,
            "zip": self.zip,
            "notes": self.notes,
        }


class CommunityMember(db.Model):
    """Tracks which users belong to a community for group message delivery."""
    __tablename__ = "community_members"
    __table_args__ = (
        sa.UniqueConstraint("community_id", "user_id", name="uix_community_member"),
    )

    membership_id = db.Column(GUID, primary_key=True, default=new_uuid)
    community_id = db.Column(GUID, db.ForeignKey("communities.community_id"), nullable=False)
    user_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    joined_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    left_at = db.Column(db.DateTime, nullable=True)

    community = db.relationship("Community")
    user = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "membership_id": str(self.membership_id),
            "community_id": str(self.community_id),
            "user_id": str(self.user_id),
            "joined_at": self.joined_at.isoformat(),
            "left_at": self.left_at.isoformat() if self.left_at else None,
        }


class GroupLeaderBinding(db.Model):
    __tablename__ = "group_leader_bindings"
    # Partial unique index enforced via DDL in the migration:
    # CREATE UNIQUE INDEX uix_glb_active ON group_leader_bindings (community_id)
    # WHERE active = 1;

    binding_id = db.Column(GUID, primary_key=True, default=new_uuid)
    community_id = db.Column(GUID, db.ForeignKey("communities.community_id"), nullable=False)
    user_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    bound_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    unbound_at = db.Column(db.DateTime, nullable=True)

    community = db.relationship("Community", back_populates="bindings")
    user = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "binding_id": str(self.binding_id),
            "community_id": str(self.community_id),
            "user_id": str(self.user_id),
            "active": self.active,
            "bound_at": self.bound_at.isoformat(),
            "unbound_at": self.unbound_at.isoformat() if self.unbound_at else None,
        }
