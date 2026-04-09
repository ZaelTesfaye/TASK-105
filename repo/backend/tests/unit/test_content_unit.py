"""
Unit tests for ContentService (HTML sanitization, versioning, rollback, attachments)
and TemplateService (schema evolution: additive vs. breaking changes, migration unblocking).

All calls go directly to the service layer, no HTTP.

Covered:
  - HTML sanitization strips <script> tags
  - HTML sanitization preserves safe tags (<p>, <b>/<strong>)
  - version number increments by 1 on each update
  - rollback restores the body of the target version
  - add_attachment rejects unsupported MIME types
  - template publish succeeds for additive-only field changes (no migration needed)
  - template publish blocked for breaking changes (field removal) without migration record
  - creating a migration record unblocks the publish
"""
import io
import uuid

import pytest

from app.services.content_service import ContentService
from app.services.template_service import TemplateService
from app.models.content import ContentItem, ContentVersion
from app.errors import AppError, UnprocessableError
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _suffix():
    return uuid.uuid4().hex[:8]


def _make_author(app):
    from app.services.auth_service import AuthService
    return AuthService.register(f"content_author_{_suffix()}", "ContentPass1!")


def _make_content(app, author, body="<p>Initial body</p>", title=None):
    """Create and return a ContentItem dict via ContentService."""
    title = title or f"Article {_suffix()}"
    return ContentService.create({
        "type": "article",
        "title": title,
        "body": body,
    }, author)


class _FakeFile:
    """Minimal file-like object that ContentService.add_attachment expects."""
    def __init__(self, data: bytes, filename: str, mimetype: str):
        self._data = data
        self.filename = filename
        self.mimetype = mimetype

    def read(self):
        return self._data


# ---------------------------------------------------------------------------
# HTML sanitization
# ---------------------------------------------------------------------------

class TestHtmlSanitization:

    def test_html_sanitization_strips_script(self, app):
        """<script> tags are stripped; only the tag itself is removed, text content may remain."""
        with app.app_context():
            author = _make_author(app)
            result = _make_content(app, author, body="<p>Hello</p><script>alert(1)</script>")

        # The script tag must be gone
        assert "<script>" not in result["body"]
        assert "</script>" not in result["body"]

    def test_html_sanitization_keeps_safe_tags(self, app):
        """<p> and <strong> (<b> is stripped but the content kept; <strong> is in the allow-list)."""
        with app.app_context():
            author = _make_author(app)
            result = _make_content(app, author, body="<p>Hello <strong>world</strong></p>")

        assert "<p>" in result["body"]
        assert "<strong>" in result["body"]
        assert "world" in result["body"]


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

class TestVersioning:

    def test_version_increments_on_update(self, app):
        """Updating a content item creates a new version number == previous version + 1."""
        with app.app_context():
            author = _make_author(app)
            created = _make_content(app, author)
            v1 = created["version"]

            updated = ContentService.update(created["content_id"], {
                "body": "<p>Updated body</p>",
            }, author)
            assert updated["version"] == v1 + 1

    def test_rollback_to_prior_version(self, app):
        """Create v1, update to v2, rollback → body matches v1 content."""
        with app.app_context():
            author = _make_author(app)
            v1_body = "<p>Version one body</p>"
            created = _make_content(app, author, body=v1_body)
            content_id = created["content_id"]
            v1_num = created["version"]

            ContentService.update(content_id, {"body": "<p>Version two body</p>"}, author)

            rolled = ContentService.rollback(content_id, v1_num, author)
            assert rolled["body"] == v1_body


# ---------------------------------------------------------------------------
# Attachment MIME type validation
# ---------------------------------------------------------------------------

class TestAttachmentMime:

    def test_attachment_mime_rejection(self, app):
        """Uploading a file with MIME type 'application/exe' raises AppError(error='unsupported_media_type')."""
        with app.app_context():
            author = _make_author(app)
            content = _make_content(app, author)

            fake_file = _FakeFile(
                data=b"MZ\x90\x00",
                filename="malware.exe",
                mimetype="application/exe",
            )

            with pytest.raises(AppError) as exc_info:
                ContentService.add_attachment(content["content_id"], fake_file, author)
            assert exc_info.value.error == "unsupported_media_type"


# ---------------------------------------------------------------------------
# Template schema evolution
# ---------------------------------------------------------------------------

class TestTemplateSchemaEvolution:

    def _make_template(self, author, fields):
        """Create a TemplateService template with the given fields list."""
        return TemplateService.create({"name": f"Tmpl-{_suffix()}", "fields": fields}, author)

    def test_template_schema_additive_no_migration(self, app):
        """
        Adding a new optional field is additive — publish must succeed without
        a migration record.
        """
        with app.app_context():
            author = _make_author(app)
            tmpl = self._make_template(author, [
                {"name": "first_name", "type": "string"},
            ])
            template_id = tmpl["template_id"]

            # Publish v1 first
            TemplateService.publish(template_id, author)

            # Add a new optional field → v2
            TemplateService.update(template_id, {
                "fields": [
                    {"name": "first_name", "type": "string"},
                    {"name": "nickname", "type": "string"},  # new optional field
                ],
            }, author)

            # Should publish without requiring a migration
            result = TemplateService.publish(template_id, author)
            assert result["status"] == "published"

    def test_template_breaking_change_requires_migration(self, app):
        """
        Removing an existing field is a breaking change — publish raises
        UnprocessableError(error='migration_required') before a migration is defined.
        """
        with app.app_context():
            author = _make_author(app)
            tmpl = self._make_template(author, [
                {"name": "first_name", "type": "string"},
                {"name": "last_name", "type": "string"},
            ])
            template_id = tmpl["template_id"]

            # Publish v1
            TemplateService.publish(template_id, author)

            # Remove a field — breaking change → v2
            TemplateService.update(template_id, {
                "fields": [
                    {"name": "first_name", "type": "string"},
                    # "last_name" removed
                ],
            }, author)

            with pytest.raises(UnprocessableError) as exc_info:
                TemplateService.publish(template_id, author)
            assert exc_info.value.error == "migration_required"

    def test_template_migration_unblocks_publish(self, app):
        """
        After creating a TemplateMigration record for the breaking change,
        publish succeeds.
        """
        with app.app_context():
            author = _make_author(app)
            tmpl = self._make_template(author, [
                {"name": "full_name", "type": "string"},
                {"name": "dob", "type": "date"},
            ])
            template_id = tmpl["template_id"]
            v1_num = tmpl["version"]

            # Publish v1
            TemplateService.publish(template_id, author)

            # Breaking change: remove 'dob' → v2
            updated = TemplateService.update(template_id, {
                "fields": [
                    {"name": "full_name", "type": "string"},
                ],
            }, author)
            v2_num = updated["version"]

            # Create the required migration record (must map removed field with a deterministic transform)
            TemplateService.create_migration(template_id, {
                "from_version": v1_num,
                "to_version": v2_num,
                "field_mappings": [
                    {"from_field": "dob", "to_field": None, "transform": "drop"},
                ],
            })

            # Publish should now succeed
            result = TemplateService.publish(template_id, author)
            assert result["status"] == "published"
            assert result["version"] == v2_num
