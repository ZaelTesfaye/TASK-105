"""
API functional tests for content and template endpoints.

Covers: content CRUD, versioning, publishing, rollback, attachment uploads (MIME/size),
        template creation/publishing, breaking-change detection, migrations, and rollback.
All tests use the Flask test client against /api/v1/content/* and /api/v1/templates/* endpoints.
"""
import io
import uuid
import pytest

BASE = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_content(client, headers, **overrides):
    payload = {
        "type": "article",
        "title": f"Test Article {uuid.uuid4().hex[:4]}",
        "body": "<p>Hello world</p>",
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/content", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json


def _upload_attachment(client, headers, content_id, data=b"hello world", filename="test.txt", mime="text/plain"):
    return client.post(
        f"{BASE}/content/{content_id}/attachments",
        data={"file": (io.BytesIO(data), filename, mime)},
        headers=headers,
        content_type="multipart/form-data",
    )


def _create_template(client, headers, **overrides):
    payload = {
        "name": f"Template_{uuid.uuid4().hex[:6]}",
        "fields": [
            {"name": "color", "type": "text", "required": False},
        ],
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/templates", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json


# ---------------------------------------------------------------------------
# Content CRUD + versioning
# ---------------------------------------------------------------------------

def test_create_content_201(client, auth_headers):
    """POST /content returns 201 with content_id/type/title/status=draft/version=1/body/created_at."""
    resp = client.post(f"{BASE}/content", json={
        "type": "article",
        "title": "My Test Article",
        "body": "<p>Test body</p>",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "content_id" in data
    assert "type" in data
    assert "title" in data
    assert data["status"] == "draft"
    assert data["version"] == 1
    assert "body" in data
    assert "created_at" in data


def test_create_content_member_forbidden(client):
    """Member token POST /content returns 403."""
    username = f"user_{uuid.uuid4().hex[:8]}"
    password = "ValidPass1234!"
    client.post(f"{BASE}/auth/register", json={
        "username": username,
        "password": password,
        "role": "Member",
    })
    token = client.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    }).json["token"]
    member_hdrs = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"{BASE}/content", json={
        "type": "article",
        "title": "Forbidden",
        "body": "<p>Not allowed</p>",
    }, headers=member_hdrs)
    assert resp.status_code == 403


def test_get_content_200(client, auth_headers):
    """GET /content/{id} returns 200."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    resp = client.get(f"{BASE}/content/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["content_id"] == cid


def test_update_content_increments_version(client, auth_headers):
    """PATCH /content/{id} returns 200 with version incremented to 2."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    resp = client.patch(f"{BASE}/content/{cid}", json={"body": "Updated body v2"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 2


def test_publish_content_200(client, auth_headers):
    """POST /content/{id}/publish returns 200 with status=published and published_at not null."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    resp = client.post(f"{BASE}/content/{cid}/publish", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "published"
    assert data["published_at"] is not None


def test_rollback_content_200(client, auth_headers):
    """Create, update, rollback to version 1 → returns 200 with version=1 body restored."""
    content = _create_content(client, auth_headers, body="v1 body")
    cid = content["content_id"]
    client.patch(f"{BASE}/content/{cid}", json={"body": "v2 body"}, headers=auth_headers)
    resp = client.post(f"{BASE}/content/{cid}/rollback", json={"target_version": 1}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 1
    current = client.get(f"{BASE}/content/{cid}", headers=auth_headers)
    assert current.json["body"] == "v1 body"


def test_list_versions_200(client, auth_headers):
    """GET /content/{id}/versions returns 200 with array of version numbers."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    client.patch(f"{BASE}/content/{cid}", json={"body": "v2"}, headers=auth_headers)
    resp = client.get(f"{BASE}/content/{cid}/versions", headers=auth_headers)
    assert resp.status_code == 200
    versions = resp.json
    assert isinstance(versions, list)
    assert len(versions) == 2
    version_nums = [v["version"] for v in versions]
    assert 1 in version_nums
    assert 2 in version_nums


def test_get_specific_version(client, auth_headers):
    """GET /content/{id}?version=1 returns body matching v1."""
    content = _create_content(client, auth_headers, body="version one body")
    cid = content["content_id"]
    client.patch(f"{BASE}/content/{cid}", json={"body": "version two body"}, headers=auth_headers)
    resp = client.get(f"{BASE}/content/{cid}?version=1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["body"] == "version one body"


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def test_attachment_upload_201(client, auth_headers):
    """POST /content/{id}/attachments (multipart) returns 201 with sha256/mime_type/size_bytes."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    resp = _upload_attachment(client, auth_headers, cid)
    assert resp.status_code == 201
    data = resp.json
    assert "sha256" in data
    assert len(data["sha256"]) == 64
    assert "mime_type" in data
    assert "size_bytes" in data


def test_attachment_unsupported_mime_415(client, auth_headers):
    """Uploading a .exe file returns 415 with error=unsupported_media_type."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    resp = _upload_attachment(client, auth_headers, cid,
                              data=b"MZ\x90\x00", filename="malware.exe",
                              mime="application/x-msdownload")
    assert resp.status_code == 415
    assert resp.json["error"] == "unsupported_media_type"


def test_attachment_too_large_413(client, auth_headers):
    """Uploading a file >25MB returns 413 with error=file_too_large."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    big_data = b"x" * (26 * 1024 * 1024)
    resp = _upload_attachment(client, auth_headers, cid,
                              data=big_data, filename="big.txt", mime="text/plain")
    assert resp.status_code == 413
    assert resp.json["error"] == "file_too_large"


def test_list_attachments_200(client, auth_headers):
    """GET /content/{id}/attachments returns 200 with array."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    _upload_attachment(client, auth_headers, cid)
    resp = client.get(f"{BASE}/content/{cid}/attachments", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)
    assert len(resp.json) >= 1


def test_delete_attachment_204(client, auth_headers):
    """DELETE /content/{id}/attachments/{att_id} returns 204."""
    content = _create_content(client, auth_headers)
    cid = content["content_id"]
    att_id = _upload_attachment(client, auth_headers, cid).json["attachment_id"]
    resp = client.delete(f"{BASE}/content/{cid}/attachments/{att_id}", headers=auth_headers)
    assert resp.status_code == 204
    # Verify it no longer appears in listing
    list_resp = client.get(f"{BASE}/content/{cid}/attachments", headers=auth_headers)
    assert not any(a["attachment_id"] == att_id for a in list_resp.json)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_create_template_201(client, auth_headers):
    """POST /templates returns 201 with template_id/version=1/status=draft."""
    resp = _create_template(client, auth_headers)
    assert "template_id" in resp
    assert resp["version"] == 1
    assert resp["status"] == "draft"


def test_publish_template_200(client, auth_headers):
    """POST /templates/{id}/publish returns 200 with status=published."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    resp = client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "published"


def test_template_additive_publish_ok(client, auth_headers):
    """Adding a new optional field and publishing returns 200 (additive change = no migration needed)."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/templates/{tid}", json={
        "fields": [
            {"name": "color", "type": "text", "required": False},
            {"name": "size", "type": "text", "required": False},
        ],
    }, headers=auth_headers)
    resp = client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    assert resp.status_code == 200


def test_template_breaking_change_blocked_422(client, auth_headers):
    """Removing a field and publishing returns 422 with error=migration_required."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/templates/{tid}", json={"fields": []}, headers=auth_headers)
    resp = client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json["error"] == "migration_required"


def test_template_migration_unblocks_publish(client, auth_headers):
    """After creating a migration record, the previously blocked publish succeeds."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/templates/{tid}", json={"fields": []}, headers=auth_headers)

    mig = client.post(f"{BASE}/templates/{tid}/migrations", json={
        "from_version": 1,
        "to_version": 2,
        "field_mappings": [{"from_field": "color", "to_field": None, "transform": "drop"}],
    }, headers=auth_headers)
    assert mig.status_code == 201

    resp = client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "published"


def test_template_rollback_200(client, auth_headers):
    """POST /templates/{id}/rollback returns 200 restoring the previous version."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/templates/{tid}", json={
        "fields": [
            {"name": "color", "type": "text", "required": False},
            {"name": "size", "type": "text", "required": False},
        ],
    }, headers=auth_headers)
    resp = client.post(f"{BASE}/templates/{tid}/rollback", json={"target_version": 1}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 1


def test_list_template_versions_200(client, auth_headers):
    """GET /templates/{id}/versions returns 200 with array of versions."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.patch(f"{BASE}/templates/{tid}", json={"name": "Updated Template"}, headers=auth_headers)
    resp = client.get(f"{BASE}/templates/{tid}/versions", headers=auth_headers)
    assert resp.status_code == 200
    versions = resp.json
    assert isinstance(versions, list)
    assert len(versions) >= 2


# ---------------------------------------------------------------------------
# Content draft isolation (SECURITY: non-privileged users must not see drafts)
# ---------------------------------------------------------------------------

def test_member_get_returns_published_not_draft(client, auth_headers, member_headers):
    """Publish v1, draft v2 → Member GET (no version param) returns v1 body, not v2."""
    content = _create_content(client, auth_headers, body="<p>Version one</p>")
    cid = content["content_id"]
    # Publish v1
    client.post(f"{BASE}/content/{cid}/publish", headers=auth_headers)
    # Create draft v2
    client.patch(f"{BASE}/content/{cid}", json={"body": "<p>Draft v2</p>"}, headers=auth_headers)

    resp = client.get(f"{BASE}/content/{cid}", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 1
    assert resp.json["body"] == "<p>Version one</p>"


def test_member_get_unpublished_content_404(client, auth_headers, member_headers):
    """Member GET on content with no published version returns 404."""
    content = _create_content(client, auth_headers)  # draft only, never published
    cid = content["content_id"]
    resp = client.get(f"{BASE}/content/{cid}", headers=member_headers)
    assert resp.status_code == 404


def test_member_get_template_returns_published_not_draft(client, auth_headers, member_headers):
    """Publish template v1, draft v2 → Member GET default returns v1 fields."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/templates/{tid}", json={
        "fields": [
            {"name": "color", "type": "text", "required": False},
            {"name": "size", "type": "text", "required": False},
        ],
    }, headers=auth_headers)
    admin_get = client.get(f"{BASE}/templates/{tid}", headers=auth_headers)
    assert admin_get.status_code == 200
    assert admin_get.json["version"] == 2

    m_resp = client.get(f"{BASE}/templates/{tid}", headers=member_headers)
    assert m_resp.status_code == 200
    assert m_resp.json["version"] == 1
    fields = m_resp.json["fields"]
    assert len(fields) == 1
    assert fields[0]["name"] == "color"


def test_admin_get_returns_draft_head(client, auth_headers):
    """Admin GET without version param sees the draft head (current_version)."""
    content = _create_content(client, auth_headers, body="<p>v1 body</p>")
    cid = content["content_id"]
    client.post(f"{BASE}/content/{cid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/content/{cid}", json={"body": "<p>v2 draft</p>"}, headers=auth_headers)

    resp = client.get(f"{BASE}/content/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 2
    assert resp.json["body"] == "<p>v2 draft</p>"


# ---------------------------------------------------------------------------
# SECURITY: member cannot read draft versions via explicit ?version= param
# ---------------------------------------------------------------------------

def test_member_cannot_read_draft_content_via_explicit_version(client, auth_headers, member_headers):
    """Member GET /content/{id}?version=2 on a draft version returns 404."""
    content = _create_content(client, auth_headers, body="<p>v1 published</p>")
    cid = content["content_id"]
    client.post(f"{BASE}/content/{cid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/content/{cid}", json={"body": "<p>v2 draft secret</p>"}, headers=auth_headers)

    # Explicit version=2 (draft) should be blocked for member
    resp = client.get(f"{BASE}/content/{cid}?version=2", headers=member_headers)
    assert resp.status_code == 404


def test_member_can_read_published_content_via_explicit_version(client, auth_headers, member_headers):
    """Member GET /content/{id}?version=1 on a published version returns 200."""
    content = _create_content(client, auth_headers, body="<p>v1 published</p>")
    cid = content["content_id"]
    client.post(f"{BASE}/content/{cid}/publish", headers=auth_headers)

    resp = client.get(f"{BASE}/content/{cid}?version=1", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 1


def test_member_cannot_read_draft_template_via_explicit_version(client, auth_headers, member_headers):
    """Member GET /templates/{id}?version=2 on a draft version returns 404."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"{BASE}/templates/{tid}", json={
        "fields": [
            {"name": "color", "type": "text", "required": False},
            {"name": "size", "type": "text", "required": False},
        ],
    }, headers=auth_headers)

    # Explicit version=2 (draft) should be blocked for member
    resp = client.get(f"{BASE}/templates/{tid}?version=2", headers=member_headers)
    assert resp.status_code == 404


def test_member_can_read_published_template_via_explicit_version(client, auth_headers, member_headers):
    """Member GET /templates/{id}?version=1 on a published version returns 200."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    client.post(f"{BASE}/templates/{tid}/publish", headers=auth_headers)

    resp = client.get(f"{BASE}/templates/{tid}?version=1", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json["version"] == 1


# ---------------------------------------------------------------------------
# SECURITY: /templates/{id}/versions restricted to management roles
# ---------------------------------------------------------------------------

def test_member_cannot_list_template_versions(client, auth_headers, member_headers):
    """Member GET /templates/{id}/versions returns 403."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    resp = client.get(f"{BASE}/templates/{tid}/versions", headers=member_headers)
    assert resp.status_code == 403


def test_admin_can_list_template_versions(client, auth_headers):
    """Admin GET /templates/{id}/versions returns 200."""
    tmpl = _create_template(client, auth_headers)
    tid = tmpl["template_id"]
    resp = client.get(f"{BASE}/templates/{tid}/versions", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)
