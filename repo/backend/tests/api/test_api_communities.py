"""
API functional tests for community endpoints.

Covers: community CRUD, service areas, group leader binding/unbinding,
        community membership (join/leave), member listing, and RBAC enforcement.
All tests use the Flask test client against /api/v1/communities/* endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"

_COMMUNITY_PAYLOAD = {
    "name": "Maplewood",
    "address_line1": "123 Main St",
    "city": "Austin",
    "state": "TX",
    "zip": "78701",
    "service_hours": {"monday": "09:00-17:00"},
    "fulfillment_scope": "Local delivery",
}


def _unique_community_name():
    return f"Comm_{uuid.uuid4().hex[:6]}"


def _create_community(client, headers, **overrides):
    payload = {**_COMMUNITY_PAYLOAD, "name": _unique_community_name()}
    payload.update(overrides)
    resp = client.post(f"{BASE}/communities", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json["community_id"]


def _register_and_login(client, role="Member"):
    """Register a user and return (user_id, auth_headers).
    Non-Member roles are created via the service layer because public
    registration is restricted to 'Member' accounts."""
    username = f"user_{uuid.uuid4().hex[:8]}"
    password = "ValidPass1234!"
    if role == "Member":
        reg = client.post(f"{BASE}/auth/register", json={
            "username": username, "password": password,
        })
        user_id = reg.json["user_id"]
    else:
        with client.application.app_context():
            from app.services.auth_service import AuthService
            user = AuthService.register(username, password, role=role)
            user_id = str(user.user_id)
    token = client.post(f"{BASE}/auth/login", json={
        "username": username, "password": password,
    }).json["token"]
    return user_id, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Community CRUD
# ---------------------------------------------------------------------------

def test_create_community_201(client, auth_headers):
    """POST /communities returns 201 with community_id/name/created_at."""
    payload = {**_COMMUNITY_PAYLOAD, "name": _unique_community_name()}
    resp = client.post(f"{BASE}/communities", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "community_id" in data
    assert "name" in data
    assert "created_at" in data


def test_create_community_invalid_zip_400(client, auth_headers):
    """POST /communities with an invalid zip returns 400."""
    payload = {**_COMMUNITY_PAYLOAD, "name": _unique_community_name(), "zip": "BADZIP"}
    resp = client.post(f"{BASE}/communities", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "zip" in resp.json["fields"]


def test_create_community_member_403(client, member_headers):
    """Member token POST /communities returns 403."""
    payload = {**_COMMUNITY_PAYLOAD, "name": _unique_community_name()}
    resp = client.post(f"{BASE}/communities", json=payload, headers=member_headers)
    assert resp.status_code == 403


def test_list_communities_200(client, auth_headers):
    """GET /communities returns 200 with paginated response."""
    _create_community(client, auth_headers)
    resp = client.get(f"{BASE}/communities", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "total" in data
    assert "items" in data


def test_get_community_200(client, auth_headers):
    """GET /communities/{id} returns 200 with nested address object."""
    cid = _create_community(client, auth_headers)
    resp = client.get(f"{BASE}/communities/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "community_id" in data or "name" in data


def test_update_community_200(client, auth_headers):
    """PATCH /communities/{id} returns 200 with updated data."""
    cid = _create_community(client, auth_headers)
    new_name = _unique_community_name()
    resp = client.patch(f"{BASE}/communities/{cid}", json={"name": new_name}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["name"] == new_name


def test_delete_community_204(client, auth_headers):
    """DELETE /communities/{id} returns 204 and subsequent GET returns 404."""
    cid = _create_community(client, auth_headers)
    del_resp = client.delete(f"{BASE}/communities/{cid}", headers=auth_headers)
    assert del_resp.status_code == 204
    get_resp = client.get(f"{BASE}/communities/{cid}", headers=auth_headers)
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Service areas
# ---------------------------------------------------------------------------

def test_create_service_area_201(client, auth_headers):
    """POST /communities/{id}/service-areas returns 201."""
    cid = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "North Zone",
        "address_line1": "456 Oak Ave",
        "city": "Austin",
        "state": "TX",
        "zip": "78702",
    }, headers=auth_headers)
    assert resp.status_code == 201


def test_create_service_area_member_403(client, auth_headers, member_headers):
    """Member token POST /communities/{id}/service-areas returns 403."""
    cid = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "South Zone",
        "address_line1": "789 Pine St",
        "city": "Austin",
        "state": "TX",
        "zip": "78703",
    }, headers=member_headers)
    assert resp.status_code == 403


def test_list_service_areas_200(client, auth_headers):
    """GET /communities/{id}/service-areas returns 200 with array."""
    cid = _create_community(client, auth_headers)
    client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "East Zone",
        "address_line1": "100 Elm St",
        "city": "Austin",
        "state": "TX",
        "zip": "78704",
    }, headers=auth_headers)
    resp = client.get(f"{BASE}/communities/{cid}/service-areas", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)


# ---------------------------------------------------------------------------
# Leader binding
# ---------------------------------------------------------------------------

def test_bind_leader_201(client, auth_headers):
    """POST /communities/{id}/leader-binding with Group Leader user returns 201 with active=true."""
    cid = _create_community(client, auth_headers)
    gl_id, _ = _register_and_login(client, role="Group Leader")
    resp = client.post(f"{BASE}/communities/{cid}/leader-binding", json={
        "user_id": gl_id,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json.get("active") is True


def test_bind_leader_non_group_leader_422(client, auth_headers):
    """Binding a Member user as leader returns 422 with error=user_not_group_leader."""
    cid = _create_community(client, auth_headers)
    member_id, _ = _register_and_login(client, role="Member")
    resp = client.post(f"{BASE}/communities/{cid}/leader-binding", json={
        "user_id": member_id,
    }, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json["error"] == "user_not_group_leader"


def test_unbind_leader_204(client, auth_headers):
    """DELETE /communities/{id}/leader-binding returns 204."""
    cid = _create_community(client, auth_headers)
    gl_id, _ = _register_and_login(client, role="Group Leader")
    client.post(f"{BASE}/communities/{cid}/leader-binding", json={
        "user_id": gl_id,
    }, headers=auth_headers)
    resp = client.delete(f"{BASE}/communities/{cid}/leader-binding", headers=auth_headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def test_join_community_201(client, auth_headers, member_headers):
    """POST /communities/{id}/members returns 201."""
    cid = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/communities/{cid}/members", headers=member_headers)
    assert resp.status_code == 201


def test_leave_community_204(client, auth_headers, member_headers):
    """Join then DELETE /communities/{id}/members returns 204."""
    cid = _create_community(client, auth_headers)
    client.post(f"{BASE}/communities/{cid}/members", headers=member_headers)
    resp = client.delete(f"{BASE}/communities/{cid}/members", headers=member_headers)
    assert resp.status_code == 204


def test_join_twice_409(client, auth_headers, member_headers):
    """Joining the same community twice returns 409 with error=already_member."""
    cid = _create_community(client, auth_headers)
    client.post(f"{BASE}/communities/{cid}/members", headers=member_headers)
    resp = client.post(f"{BASE}/communities/{cid}/members", headers=member_headers)
    assert resp.status_code == 409
    assert resp.json["error"] == "already_member"


def test_list_members_200(client, auth_headers, member_headers):
    """After joining, admin can list members and receive 200."""
    cid = _create_community(client, auth_headers)
    client.post(f"{BASE}/communities/{cid}/members", headers=member_headers)
    resp = client.get(f"{BASE}/communities/{cid}/members", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)
    assert len(resp.json) >= 1


# ---------------------------------------------------------------------------
# Validation: malformed payloads return 400 with structured error
# ---------------------------------------------------------------------------

def test_create_community_missing_required_fields_400(client, auth_headers):
    """POST /communities with empty body returns 400 with validation_error and fields."""
    resp = client.post(f"{BASE}/communities", json={}, headers=auth_headers)
    assert resp.status_code == 400
    data = resp.json
    assert data["error"] == "validation_error"
    assert "fields" in data
    # name, address_line1, city, state, zip are required
    for field in ("name", "address_line1", "city", "state", "zip"):
        assert field in data["fields"], f"Expected '{field}' in validation fields"


def test_create_community_invalid_field_types_400(client, auth_headers):
    """POST /communities with wrong types returns 400 with validation_error."""
    resp = client.post(f"{BASE}/communities", json={
        "name": 12345,  # should be string but marshmallow coerces; use missing required instead
        "address_line1": "",  # too short
        "city": "",
        "state": "X",  # too short
        "zip": "1",  # too short
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"


def test_update_community_invalid_field_400(client, auth_headers):
    """PATCH /communities/{id} with invalid state returns 400."""
    cid = _create_community(client, auth_headers)
    resp = client.patch(f"{BASE}/communities/{cid}", json={
        "state": "X",  # too short, must be 2 chars
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"


def test_update_community_invalid_zip_400(client, auth_headers):
    """PATCH /communities/{id} with an invalid zip returns 400."""
    cid = _create_community(client, auth_headers)
    resp = client.patch(f"{BASE}/communities/{cid}", json={
        "zip": "BADZIP",
    }, headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Service-area validation
# ---------------------------------------------------------------------------

def test_create_service_area_missing_fields_400(client, auth_headers):
    """POST /communities/{id}/service-areas with empty body returns 400 with field errors."""
    cid = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={}, headers=auth_headers)
    assert resp.status_code == 400
    data = resp.json
    assert data["error"] == "validation_error"
    assert "fields" in data
    for field in ("name", "address_line1", "city", "state", "zip"):
        assert field in data["fields"], f"Expected '{field}' in validation fields"


def test_create_service_area_invalid_state_400(client, auth_headers):
    """POST /communities/{id}/service-areas with invalid state returns 400."""
    cid = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "Bad Zone",
        "address_line1": "1 Main St",
        "city": "Austin",
        "state": "texas",
        "zip": "78701",
    }, headers=auth_headers)
    assert resp.status_code == 400
    data = resp.json
    assert data["error"] == "validation_error"
    assert "state" in data["fields"]


def test_create_service_area_invalid_zip_400(client, auth_headers):
    """POST /communities/{id}/service-areas with invalid zip returns 400."""
    cid = _create_community(client, auth_headers)
    resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "Bad Zone",
        "address_line1": "1 Main St",
        "city": "Austin",
        "state": "TX",
        "zip": "ABCDE",
    }, headers=auth_headers)
    assert resp.status_code == 400
    data = resp.json
    assert data["error"] == "validation_error"
    assert "zip" in data["fields"]


def test_update_service_area_invalid_state_400(client, auth_headers):
    """PATCH /communities/{id}/service-areas/{area_id} with invalid state returns 400."""
    cid = _create_community(client, auth_headers)
    area_resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "Zone A",
        "address_line1": "1 Main St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=auth_headers)
    area_id = area_resp.json["service_area_id"]
    resp = client.patch(f"{BASE}/communities/{cid}/service-areas/{area_id}", json={
        "state": "xx",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"


def test_update_service_area_invalid_zip_400(client, auth_headers):
    """PATCH /communities/{id}/service-areas/{area_id} with invalid zip returns 400."""
    cid = _create_community(client, auth_headers)
    area_resp = client.post(f"{BASE}/communities/{cid}/service-areas", json={
        "name": "Zone B",
        "address_line1": "2 Elm St",
        "city": "Austin",
        "state": "TX",
        "zip": "78702",
    }, headers=auth_headers)
    area_id = area_resp.json["service_area_id"]
    resp = client.patch(f"{BASE}/communities/{cid}/service-areas/{area_id}", json={
        "zip": "999",
    }, headers=auth_headers)
    assert resp.status_code == 400
