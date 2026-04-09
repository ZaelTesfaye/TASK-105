from datetime import datetime, timezone
import sqlalchemy as sa
from app.extensions import db
from .base import GUID, new_uuid

CONTENT_TYPES = ("article", "book", "chapter")
CONTENT_STATUSES = ("draft", "published")
ALLOWED_MIME_TYPES = ("image/png", "image/jpeg", "application/pdf", "text/plain", "text/markdown")
ALLOWED_MIME = set(ALLOWED_MIME_TYPES)
MAX_ATTACHMENT_BYTES = 26_214_400  # 25 MB


class ContentItem(db.Model):
    __tablename__ = "content_items"
    __table_args__ = (
        sa.CheckConstraint(
            "type IN ('article', 'book', 'chapter')",
            name="ck_content_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_content_status",
        ),
    )

    content_id = db.Column(GUID, primary_key=True, default=new_uuid)
    type = db.Column(db.String(16), nullable=False)
    # chapter → book self-reference; NULL for article / top-level book
    parent_id = db.Column(GUID, db.ForeignKey("content_items.content_id"), nullable=True)
    title = db.Column(db.String(512), nullable=False)
    # Tracks which version number is currently active
    current_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(16), nullable=False, default="draft")
    created_by = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    versions = db.relationship(
        "ContentVersion",
        back_populates="content_item",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    attachments = db.relationship(
        "Attachment", back_populates="content_item", lazy="dynamic"
    )

    def to_dict(self) -> dict:
        return {
            "content_id": str(self.content_id),
            "type": self.type,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "title": self.title,
            "current_version": self.current_version,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class ContentVersion(db.Model):
    """
    Immutable version records — once written they are never updated (rollback works
    by changing content_items.current_version, not by mutating version rows).
    """
    __tablename__ = "content_versions"
    __table_args__ = (
        db.UniqueConstraint("content_id", "version", name="uix_cv"),
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_cv_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_cv_version_positive"),
    )

    version_id = db.Column(GUID, primary_key=True, default=new_uuid)
    content_id = db.Column(
        GUID, db.ForeignKey("content_items.content_id"), nullable=False, index=True
    )
    version = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False, default="")     # sanitized Markdown/HTML
    tags = db.Column(db.Text, nullable=False, default="[]")       # JSON array
    categories = db.Column(db.Text, nullable=False, default="[]")  # JSON array
    status = db.Column(db.String(16), nullable=False, default="draft")
    published_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    content_item = db.relationship("ContentItem", back_populates="versions")

    def to_dict(self) -> dict:
        import json
        return {
            "version_id": str(self.version_id),
            "content_id": str(self.content_id),
            "version": self.version,
            "body": self.body,
            "tags": json.loads(self.tags),
            "categories": json.loads(self.categories),
            "status": self.status,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat(),
        }


class Attachment(db.Model):
    """
    Local-storage file attachment. Exactly one of content_id or template_id must be set.
    sha256 is computed from file bytes server-side; used for dedup detection.
    Soft-deleted rows are cleaned up by the daily attachment_cleanup job.
    """
    __tablename__ = "attachments"
    __table_args__ = (
        sa.CheckConstraint(
            "mime_type IN ('image/png', 'image/jpeg', 'application/pdf', 'text/plain', 'text/markdown')",
            name="ck_attachment_mime",
        ),
        sa.CheckConstraint(
            f"size_bytes > 0 AND size_bytes <= {MAX_ATTACHMENT_BYTES}",
            name="ck_attachment_size",
        ),
        # Exactly one owner — content item or template, not both, not neither
        sa.CheckConstraint(
            "(content_id IS NOT NULL) != (template_id IS NOT NULL)",
            name="ck_attachment_single_owner",
        ),
    )

    attachment_id = db.Column(GUID, primary_key=True, default=new_uuid)
    content_id = db.Column(
        GUID, db.ForeignKey("content_items.content_id"), nullable=True
    )
    template_id = db.Column(
        GUID, db.ForeignKey("capture_templates.template_id"), nullable=True
    )
    filename = db.Column(db.String(256), nullable=False)
    mime_type = db.Column(db.String(64), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    local_path = db.Column(db.Text, nullable=False)
    created_by = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    content_item = db.relationship("ContentItem", back_populates="attachments")

    def to_dict(self) -> dict:
        return {
            "attachment_id": str(self.attachment_id),
            "content_id": str(self.content_id) if self.content_id else None,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at.isoformat(),
        }


class CaptureTemplate(db.Model):
    __tablename__ = "capture_templates"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_template_status",
        ),
    )

    template_id = db.Column(GUID, primary_key=True, default=new_uuid)
    name = db.Column(db.String(256), nullable=False)
    current_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(16), nullable=False, default="draft")
    created_by = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    versions = db.relationship(
        "TemplateVersion",
        back_populates="template",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    migrations = db.relationship(
        "TemplateMigration", back_populates="template", lazy="dynamic"
    )

    def to_dict(self) -> dict:
        return {
            "template_id": str(self.template_id),
            "name": self.name,
            "current_version": self.current_version,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class TemplateVersion(db.Model):
    """
    Immutable once published. Version rows are never deleted — rollback
    changes capture_templates.current_version, not this table.
    """
    __tablename__ = "template_versions"
    __table_args__ = (
        db.UniqueConstraint("template_id", "version", name="uix_tv"),
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_tv_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_tv_version_positive"),
    )

    tv_id = db.Column(GUID, primary_key=True, default=new_uuid)
    template_id = db.Column(
        GUID, db.ForeignKey("capture_templates.template_id"), nullable=False, index=True
    )
    version = db.Column(db.Integer, nullable=False)
    fields = db.Column(db.Text, nullable=False, default="[]")  # JSON field definitions
    status = db.Column(db.String(16), nullable=False, default="draft")
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    template = db.relationship("CaptureTemplate", back_populates="versions")

    def to_dict(self) -> dict:
        import json
        return {
            "tv_id": str(self.tv_id),
            "template_id": str(self.template_id),
            "version": self.version,
            "fields": json.loads(self.fields),
            "status": self.status,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat(),
        }


class TemplateMigration(db.Model):
    """
    Required before publishing a non-additive template version change.
    One migration record per (template, from_version, to_version) pair.
    field_mappings JSON: [{from_field, to_field, transform: 'identity'|'concat'|'default:<v>'}]
    """
    __tablename__ = "template_migrations"
    __table_args__ = (
        db.UniqueConstraint("template_id", "from_version", "to_version", name="uix_tmig"),
        sa.CheckConstraint("from_version >= 1", name="ck_tmig_from_positive"),
        sa.CheckConstraint("to_version > from_version", name="ck_tmig_forward_only"),
    )

    migration_id = db.Column(GUID, primary_key=True, default=new_uuid)
    template_id = db.Column(
        GUID, db.ForeignKey("capture_templates.template_id"), nullable=False, index=True
    )
    from_version = db.Column(db.Integer, nullable=False)
    to_version = db.Column(db.Integer, nullable=False)
    field_mappings = db.Column(db.Text, nullable=False, default="[]")  # JSON
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    template = db.relationship("CaptureTemplate", back_populates="migrations")

    def to_dict(self) -> dict:
        import json
        return {
            "migration_id": str(self.migration_id),
            "template_id": str(self.template_id),
            "from_version": self.from_version,
            "to_version": self.to_version,
            "field_mappings": json.loads(self.field_mappings),
            "created_at": self.created_at.isoformat(),
        }
