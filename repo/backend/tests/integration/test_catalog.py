"""Product catalog and search tests."""


_PRODUCT = {
    "sku": "WIDGET-001",
    "name": "Widget",
    "brand": "Acme",
    "category": "Tools",
    "description": "A useful widget",
    "price_usd": 9.99,
    "tags": ["popular"],
}


def test_create_product(client, auth_headers):
    resp = client.post("/api/v1/products", json=_PRODUCT, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["sku"] == "WIDGET-001"


def test_get_product(client, auth_headers):
    create_resp = client.post("/api/v1/products", json={**_PRODUCT, "sku": "WIDGET-GET"}, headers=auth_headers)
    pid = create_resp.json["product_id"]
    resp = client.get(f"/api/v1/products/{pid}", headers=auth_headers)
    assert resp.status_code == 200


def test_duplicate_sku(client, auth_headers):
    client.post("/api/v1/products", json={**_PRODUCT, "sku": "DUP-SKU"}, headers=auth_headers)
    resp = client.post("/api/v1/products", json={**_PRODUCT, "sku": "DUP-SKU"}, headers=auth_headers)
    assert resp.status_code == 409


def test_search_products(client, auth_headers):
    client.post("/api/v1/products", json={**_PRODUCT, "sku": "SEARCH-001"}, headers=auth_headers)
    resp = client.get("/api/v1/search/products?q=Widget", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json


def test_search_history(client, auth_headers):
    client.get("/api/v1/search/products?q=Gadget", headers=auth_headers)
    resp = client.get("/api/v1/search/history", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json["history"], list)


def test_delete_product(client, auth_headers):
    create_resp = client.post("/api/v1/products", json={**_PRODUCT, "sku": "DEL-PROD"}, headers=auth_headers)
    pid = create_resp.json["product_id"]
    resp = client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Attribute-based search filters (Fix 2)
# ---------------------------------------------------------------------------

def test_search_by_attribute_filter(client, auth_headers):
    """Search with attributes[color]=red should return only matching products."""
    import uuid
    sku1 = f"ATTR-RED-{uuid.uuid4().hex[:6]}"
    sku2 = f"ATTR-BLU-{uuid.uuid4().hex[:6]}"
    client.post("/api/v1/products", json={
        **_PRODUCT, "sku": sku1, "name": "Red Widget",
        "attributes": [{"key": "color", "value": "red"}],
    }, headers=auth_headers)
    client.post("/api/v1/products", json={
        **_PRODUCT, "sku": sku2, "name": "Blue Widget",
        "attributes": [{"key": "color", "value": "blue"}],
    }, headers=auth_headers)

    resp = client.get("/api/v1/search/products?q=Widget&attributes[color]=red",
                      headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json["items"]
    skus = [i["sku"] for i in items]
    assert sku1 in skus
    assert sku2 not in skus


def test_search_by_multiple_attributes(client, auth_headers):
    """Search with multiple attribute filters narrows results."""
    import uuid
    sku = f"ATTR-MULTI-{uuid.uuid4().hex[:6]}"
    client.post("/api/v1/products", json={
        **_PRODUCT, "sku": sku, "name": "Premium Widget",
        "attributes": [
            {"key": "color", "value": "green"},
            {"key": "size", "value": "large"},
        ],
    }, headers=auth_headers)

    # Both attributes match
    resp = client.get(
        "/api/v1/search/products?q=Premium&attributes[color]=green&attributes[size]=large",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert any(i["sku"] == sku for i in resp.json["items"])

    # Wrong size → no match
    resp2 = client.get(
        "/api/v1/search/products?q=Premium&attributes[color]=green&attributes[size]=small",
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert not any(i["sku"] == sku for i in resp2.json["items"])
