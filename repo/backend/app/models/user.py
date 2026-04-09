from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, EncryptedText, new_uuid

ROLES = (
    "Administrator",
    "Operations Manager",
    "Moderator",
    "Group Leader",
    "Staff",
    "Member",
)

_ROLE_LIST = ", ".join(f"'{r}'" for r in ROLES)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint(
            f"role IN ({_ROLE_LIST})",
            name="ck_users_role",
        ),
    )

    user_id = db.Column(GUID, primary_key=True, default=new_uuid)
    username = db.Column(db.String(64), unique=True, nullable=False)
    # bcrypt hash stored Fernet-encrypted at rest
    password_hash = db.Column(EncryptedText, nullable=False)
    role = db.Column(db.String(32), nullable=False, default="Member")
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    sessions = db.relationship(
        "Session", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until.replace(
            tzinfo=timezone.utc
        )

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


class Session(db.Model):
    __tablename__ = "sessions"

    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", back_populates="sessions")
