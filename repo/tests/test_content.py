"""
Content, template, and attachment endpoint tests.
Covers: versioning, publish/rollback, sanitized body storage, attachments
        (MIME, size limit, sha256), template migration requirement, RBAC.
"""
import io
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content(client, headers, **kwargs):
    payload = {"type": "article", "title": "Test", "body": "<p>Hello</p>"}
    payload.update(kwargs)
    resp = client.post("/api/v1/content", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json


def _template(client, headers, **kwargs):
    payload = {"name": f"T-{uuid.uuid4().hex[:6]}", "fields": [
        {"name": "color", "type": "text", "required": False}
    ]}
    payload.update(kwargs)
    resp = client.post("/api/v1/templates", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json


# ---------------------------------------------------------------------------
# Content CRUD + versioning
# ---------------------------------------------------------------------------

def test_create_and_publish_article(client, auth_headers):
    d = _content(client, auth_headers)
    assert d["status"] == "draft"
    cid = d["content_id"]

    pub = client.post(f"/api/v1/content/{cid}/publish", headers=auth_headers)
    assert pub.status_code == 200
    assert pub.json["status"] == "published"
    assert pub.json["published_at"] is not None


def test_content_version_increment(client, auth_headers):
    d = _content(client, auth_headers)
    cid = d["content_id"]

    upd = client.patch(f"/api/v1/content/{cid}", json={"body": "v2"}, headers=auth_headers)
    assert upd.status_code == 200
    assert upd.json["version"] == 2


def test_content_body_sanitized(client, auth_headers):
    """Dangerous HTML is stripped; allowed tags survive."""
    d = _content(client, auth_headers,
                 body='<p>Safe</p><script>alert(1)</script><em>em</em>')
    cid = d["content_id"]
    resp = client.get(f"/api/v1/content/{cid}", headers=auth_headers)
    body = resp.json["body"]
    assert "<script>" not in body
    assert "Safe" in body
    assert "<em>em</em>" in body


def test_content_rollback(client, auth_headers):
    """Rollback restores the version pointer to an older version."""
    d = _content(client, auth_headers, body="v1 body")
    cid = d["content_id"]

    # Create v2
    client.patch(f"/api/v1/content/{cid}", json={"body": "v2 body"}, headers=auth_headers)
    # Rollback to v1
    rb = client.post(f"/api/v1/content/{cid}/rollback",
                     json={"target_version": 1}, headers=auth_headers)
    assert rb.status_code == 200
    assert rb.json["version"] == 1

    # GET should now return v1 body
    current = client.get(f"/api/v1/content/{cid}", headers=auth_headers)
    assert current.json["body"] == "v1 body"


def test_content_list_versions(client, auth_headers):
    d = _content(client, auth_headers)
    cid = d["content_id"]
    client.patch(f"/api/v1/content/{cid}", json={"body": "v2"}, headers=auth_headers)

    resp = client.get(f"/api/v1/content/{cid}/versions", headers=auth_headers)
    assert resp.status_code == 200
    versions = resp.json
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2


def test_content_get_specific_version(client, auth_headers):
    d = _content(client, auth_headers, body="version one")
    cid = d["content_id"]
    client.patch(f"/api/v1/content/{cid}", json={"body": "version two"}, headers=auth_headers)

    resp = client.get(f"/api/v1/content/{cid}?version=1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["body"] == "version one"


def test_content_not_found(client, auth_headers):
    resp = client.get(f"/api/v1/content/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _upload_attachment(client, headers, content_id, data=b"hello", filename="f.txt", mime="text/plain"):
    return client.post(
        f"/api/v1/content/{content_id}/attachments",
        data={"file": (io.BytesIO(data), filename, mime)},
        headers=headers,
        content_type="multipart/form-data",
    )


def test_attachment_upload_and_list(client, auth_headers):
    cid = _content(client, auth_headers)["content_id"]
    resp = _upload_attachment(client, auth_headers, cid)
    assert resp.status_code == 201
    d = resp.json
    assert "attachment_id" in d
    assert d["mime_type"] == "text/plain"
    assert d["sha256"] is not None and len(d["sha256"]) == 64

    list_resp = client.get(f"/api/v1/content/{cid}/attachments", headers=auth_headers)
    assert list_resp.status_code == 200
    assert any(a["attachment_id"] == d["attachment_id"] for a in list_resp.json)


def test_attachment_sha256_correct(client, auth_headers):
    import hashlib
    data = b"deterministic content"
    cid = _content(client, auth_headers)["content_id"]
    resp = _upload_attachment(client, auth_headers, cid, data=data)
    assert resp.status_code == 201
    expected = hashlib.sha256(data).hexdigest()
    assert resp.json["sha256"] == expected


def test_attachment_disallowed_mime_rejected(client, auth_headers):
    cid = _content(client, auth_headers)["content_id"]
    resp = _upload_attachment(client, auth_headers, cid,
                              data=b"video", filename="v.mp4", mime="video/mp4")
    assert resp.status_code == 415
    assert resp.json["error"] == "unsupported_media_type"


def test_attachment_size_limit_enforced(client, auth_headers):
    cid = _content(client, auth_headers)["content_id"]
    # 25 MB + 1 byte
    big = b"x" * (25 * 1024 * 1024 + 1)
    resp = _upload_attachment(client, auth_headers, cid, data=big)
    assert resp.status_code == 413
    assert resp.json["error"] == "file_too_large"


def test_attachment_soft_delete(client, auth_headers):
    cid = _content(client, auth_headers)["content_id"]
    att_id = _upload_attachment(client, auth_headers, cid).json["attachment_id"]

    del_resp = client.delete(
        f"/api/v1/content/{cid}/attachments/{att_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    # Should no longer appear in listing
    list_resp = client.get(f"/api/v1/content/{cid}/attachments", headers=auth_headers)
    assert not any(a["attachment_id"] == att_id for a in list_resp.json)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_create_template(client, auth_headers):
    resp = _template(client, auth_headers)
    assert resp["status"] == "draft"
    assert "template_id" in resp


def test_template_publish_v1(client, auth_headers):
    tid = _template(client, auth_headers)["template_id"]
    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 200
    assert pub.json["status"] == "published"


def test_template_migration_required_on_breaking_change(client, auth_headers):
    tid = _template(client, auth_headers)["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Remove field (non-additive)
    client.patch(f"/api/v1/templates/{tid}", json={"fields": []}, headers=auth_headers)

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 422
    assert pub.json["error"] == "migration_required"


def test_template_additive_publish_no_migration_needed(client, auth_headers):
    """Adding a new optional field does NOT require a migration."""
    tid = _template(client, auth_headers)["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Add field (additive)
    client.patch(f"/api/v1/templates/{tid}", json={"fields": [
        {"name": "color", "type": "text", "required": False},
        {"name": "size", "type": "text", "required": False},  # new field
    ]}, headers=auth_headers)

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 200


def test_template_create_migration_and_publish(client, auth_headers):
    """With migration record present, non-additive publish succeeds."""
    tid = _template(client, auth_headers)["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Remove field
    client.patch(f"/api/v1/templates/{tid}", json={"fields": []}, headers=auth_headers)

    # Create migration mapping
    mig = client.post(f"/api/v1/templates/{tid}/migrations", json={
        "from_version": 1, "to_version": 2,
        "field_mappings": [{"from_field": "color", "to_field": None, "transform": "drop"}],
    }, headers=auth_headers)
    assert mig.status_code == 201

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 200
    assert pub.json["status"] == "published"


def test_template_rollback(client, auth_headers):
    tid = _template(client, auth_headers)["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Add a new field
    client.patch(f"/api/v1/templates/{tid}", json={"fields": [
        {"name": "color", "type": "text", "required": False},
        {"name": "size", "type": "text", "required": False},
    ]}, headers=auth_headers)

    rb = client.post(f"/api/v1/templates/{tid}/rollback",
                     json={"target_version": 1}, headers=auth_headers)
    assert rb.status_code == 200
    assert rb.json["version"] == 1
    assert len(rb.json["fields"]) == 1  # original single field


def test_template_list_versions(client, auth_headers):
    tid = _template(client, auth_headers)["template_id"]
    client.patch(f"/api/v1/templates/{tid}", json={"name": "Updated"}, headers=auth_headers)

    resp = client.get(f"/api/v1/templates/{tid}/versions", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json) == 2


def test_template_type_change_requires_migration(client, auth_headers):
    """Changing a field's type is non-additive → migration required."""
    tid = _template(client, auth_headers, fields=[
        {"name": "qty", "type": "text", "required": False}
    ])["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Change type text → number
    client.patch(f"/api/v1/templates/{tid}", json={"fields": [
        {"name": "qty", "type": "number", "required": False}
    ]}, headers=auth_headers)

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 422
    assert pub.json["error"] == "migration_required"


# ---------------------------------------------------------------------------
# Template migration schema validation (Fix 1)
# ---------------------------------------------------------------------------

def test_template_empty_migration_rejected_on_publish(client, auth_headers):
    """Migration with empty field_mappings must be rejected at publish time."""
    tid = _template(client, auth_headers, fields=[
        {"name": "color", "type": "text", "required": False}
    ])["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Remove field (non-additive)
    client.patch(f"/api/v1/templates/{tid}", json={"fields": []}, headers=auth_headers)
    # Create migration with empty field_mappings
    mig = client.post(f"/api/v1/templates/{tid}/migrations", json={
        "from_version": 1, "to_version": 2, "field_mappings": [],
    }, headers=auth_headers)
    assert mig.status_code == 201

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 422
    assert pub.json["error"] == "migration_incomplete"


def test_template_migration_invalid_transform_rejected(client, auth_headers):
    """Migration with unknown transform is rejected at creation time."""
    tid = _template(client, auth_headers, fields=[
        {"name": "color", "type": "text", "required": False}
    ])["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"/api/v1/templates/{tid}", json={"fields": []}, headers=auth_headers)

    mig = client.post(f"/api/v1/templates/{tid}/migrations", json={
        "from_version": 1, "to_version": 2,
        "field_mappings": [{"from_field": "color", "to_field": None, "transform": "eval"}],
    }, headers=auth_headers)
    assert mig.status_code == 422
    assert mig.json["error"] == "migration_invalid_transform"


def test_template_migration_incomplete_coverage_rejected(client, auth_headers):
    """Migration that doesn't cover all removed fields is rejected on publish."""
    tid = _template(client, auth_headers, fields=[
        {"name": "color", "type": "text", "required": False},
        {"name": "size", "type": "text", "required": False},
    ])["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    # Remove both fields
    client.patch(f"/api/v1/templates/{tid}", json={"fields": []}, headers=auth_headers)
    # Migration covers only 'color', not 'size'
    client.post(f"/api/v1/templates/{tid}/migrations", json={
        "from_version": 1, "to_version": 2,
        "field_mappings": [{"from_field": "color", "to_field": None, "transform": "drop"}],
    }, headers=auth_headers)

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 422
    assert pub.json["error"] == "migration_incomplete"


def test_template_migration_complete_coverage_succeeds(client, auth_headers):
    """Migration covering all removed fields with valid transforms allows publish."""
    tid = _template(client, auth_headers, fields=[
        {"name": "color", "type": "text", "required": False},
        {"name": "size", "type": "text", "required": False},
    ])["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"/api/v1/templates/{tid}", json={"fields": []}, headers=auth_headers)
    # Migration covers both fields
    client.post(f"/api/v1/templates/{tid}/migrations", json={
        "from_version": 1, "to_version": 2,
        "field_mappings": [
            {"from_field": "color", "to_field": None, "transform": "drop"},
            {"from_field": "size", "to_field": None, "transform": "drop"},
        ],
    }, headers=auth_headers)

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 200
    assert pub.json["status"] == "published"


def test_template_migration_default_transform_accepted(client, auth_headers):
    """The 'default:<value>' transform is accepted as deterministic."""
    tid = _template(client, auth_headers, fields=[
        {"name": "color", "type": "text", "required": False}
    ])["template_id"]
    client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    client.patch(f"/api/v1/templates/{tid}", json={"fields": [
        {"name": "color", "type": "number", "required": False}
    ]}, headers=auth_headers)

    mig = client.post(f"/api/v1/templates/{tid}/migrations", json={
        "from_version": 1, "to_version": 2,
        "field_mappings": [{"from_field": "color", "to_field": "color", "transform": "default:0"}],
    }, headers=auth_headers)
    assert mig.status_code == 201

    pub = client.post(f"/api/v1/templates/{tid}/publish", headers=auth_headers)
    assert pub.status_code == 200
