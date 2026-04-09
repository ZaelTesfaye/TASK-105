"""Community and service area endpoint tests."""


_COMMUNITY_PAYLOAD = {
    "name": "Maplewood",
    "address_line1": "123 Main St",
    "city": "Austin",
    "state": "TX",
    "zip": "78701",
    "service_hours": {"monday": "09:00-17:00"},
    "fulfillment_scope": "Local delivery",
}


def test_create_community(client, auth_headers):
    resp = client.post("/api/v1/communities", json=_COMMUNITY_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["name"] == "Maplewood"


def test_list_communities(client, auth_headers):
    client.post("/api/v1/communities", json=_COMMUNITY_PAYLOAD, headers=auth_headers)
    resp = client.get("/api/v1/communities", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["total"] >= 1


def test_get_community(client, auth_headers):
    create_resp = client.post("/api/v1/communities", json=_COMMUNITY_PAYLOAD, headers=auth_headers)
    cid = create_resp.json["community_id"]
    resp = client.get(f"/api/v1/communities/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert "active_group_leader" in resp.json


def test_create_service_area(client, auth_headers):
    create_resp = client.post("/api/v1/communities", json=_COMMUNITY_PAYLOAD, headers=auth_headers)
    cid = create_resp.json["community_id"]
    resp = client.post(f"/api/v1/communities/{cid}/service-areas", headers=auth_headers, json={
        "name": "North Zone", "address_line1": "456 Oak Ave", "city": "Austin", "state": "TX", "zip": "78702",
    })
    assert resp.status_code == 201


def test_invalid_zip(client, auth_headers):
    payload = {**_COMMUNITY_PAYLOAD, "zip": "ABCDE"}
    resp = client.post("/api/v1/communities", json=payload, headers=auth_headers)
    assert resp.status_code == 400
