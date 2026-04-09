"""
API functional tests for product catalog and search endpoints.

Covers: product CRUD, SKU uniqueness, RBAC enforcement, search with pagination,
        zero-result guidance, autocomplete, search history, trending, and safety stock.
All tests use the Flask test client against /api/v1/products/* and /api/v1/search/* endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"


def _unique_sku():
    return f"SKU-{uuid.uuid4().hex[:8].upper()}"


def _create_product(client, headers, sku=None, **overrides):
    if sku is None:
        sku = _unique_sku()
    payload = {
        "sku": sku,
        "name": f"Test Product {uuid.uuid4().hex[:4]}",
        "brand": "TestBrand",
        "category": "Electronics",
        "description": "A test product",
        "price_usd": 29.99,
    }
    payload.update(overrides)
    return client.post(f"{BASE}/products", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------

def test_create_product_201(client, auth_headers):
    """POST /products returns 201 with product_id/sku/name/brand/category/price_usd/created_at."""
    resp = _create_product(client, auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "product_id" in data
    assert "sku" in data
    assert "name" in data
    assert "brand" in data
    assert "category" in data
    assert "price_usd" in data
    assert "created_at" in data


def test_create_product_sku_taken_409(client, auth_headers):
    """Duplicate SKU returns 409 with error=sku_taken."""
    sku = _unique_sku()
    _create_product(client, auth_headers, sku=sku)
    resp = _create_product(client, auth_headers, sku=sku)
    assert resp.status_code == 409
    assert resp.json["error"] == "sku_taken"


def test_create_product_member_403(client, member_headers):
    """Member token POST /products returns 403 with error=forbidden."""
    resp = _create_product(client, member_headers)
    assert resp.status_code == 403


def test_get_product_200(client, auth_headers):
    """GET /products/{id} returns 200."""
    product_id = _create_product(client, auth_headers).json["product_id"]
    resp = client.get(f"{BASE}/products/{product_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["product_id"] == product_id


def test_get_product_not_found_404(client, auth_headers):
    """GET /products/{random_uuid} returns 404 with error=not_found."""
    resp = client.get(f"{BASE}/products/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json["error"] == "not_found"


def test_update_product_200(client, auth_headers):
    """PATCH /products/{id} returns 200 with updated name."""
    product_id = _create_product(client, auth_headers).json["product_id"]
    new_name = f"Updated Product {uuid.uuid4().hex[:4]}"
    resp = client.patch(f"{BASE}/products/{product_id}", json={"name": new_name}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["name"] == new_name


def test_delete_product_204(client, auth_headers):
    """DELETE /products/{id} returns 204 and subsequent GET returns 404."""
    product_id = _create_product(client, auth_headers).json["product_id"]
    del_resp = client.delete(f"{BASE}/products/{product_id}", headers=auth_headers)
    assert del_resp.status_code == 204
    get_resp = client.get(f"{BASE}/products/{product_id}", headers=auth_headers)
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search_products_200(client, auth_headers):
    """GET /search/products?q=test returns 200 with total/items."""
    # Create a product first so we have something to search
    _create_product(client, auth_headers, name="test_searchable_item")
    resp = client.get(f"{BASE}/search/products?q=test", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "total" in data
    assert "items" in data


def test_search_zero_result_guidance(client, auth_headers):
    """Searching for a non-existent term returns total=0 and zero_result_guidance is not None."""
    resp = client.get(f"{BASE}/search/products?q=xyzzy_notexist_9999", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert data["total"] == 0
    assert data.get("zero_result_guidance") is not None


def test_search_zero_result_fuzzy_brand_guidance(client, auth_headers):
    """Typo / near-miss query returns closest brand suggestions via fuzzy matching."""
    suffix = uuid.uuid4().hex[:8]
    brand = f"FuzzyBrand_{suffix}"
    typo = f"FuzzyBrnad_{suffix}"  # transposed letters in "Brand"
    _create_product(client, auth_headers, name="Rare SKU item", brand=brand, sku=f"ZYZ-{uuid.uuid4().hex[:6]}")
    resp = client.get(f"{BASE}/search/products?q={typo}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert data["total"] == 0
    g = data.get("zero_result_guidance") or {}
    brands = g.get("closest_brands") or []
    assert brand in brands, f"expected fuzzy hit for {brand!r} in {brands!r}"


def test_search_autocomplete_200(client, auth_headers):
    """GET /search/autocomplete?q=par returns 200 with suggestions list."""
    resp = client.get(f"{BASE}/search/autocomplete?q=par", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


def test_search_history_200(client, auth_headers):
    """After a search, GET /search/history has an entry with the query."""
    query_term = f"hist_{uuid.uuid4().hex[:6]}"
    client.get(f"{BASE}/search/products?q={query_term}", headers=auth_headers)
    resp = client.get(f"{BASE}/search/history", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    history = data.get("history", data) if isinstance(data, dict) else data
    assert isinstance(history, list)
    assert any(entry.get("query") == query_term for entry in history)


def test_delete_search_history_204(client, auth_headers):
    """DELETE /search/history returns 204 and history is empty afterwards."""
    client.get(f"{BASE}/search/products?q=something", headers=auth_headers)
    del_resp = client.delete(f"{BASE}/search/history", headers=auth_headers)
    assert del_resp.status_code == 204
    hist_resp = client.get(f"{BASE}/search/history", headers=auth_headers)
    assert hist_resp.status_code == 200
    data = hist_resp.json
    history = data.get("history", data) if isinstance(data, dict) else data
    assert history == []


def test_trending_200(client, auth_headers):
    """GET /search/trending returns 200 with trending list."""
    resp = client.get(f"{BASE}/search/trending", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "trending" in data
    assert isinstance(data["trending"], list)


# ---------------------------------------------------------------------------
# Safety stock
# ---------------------------------------------------------------------------

def test_set_safety_stock_200(client, auth_headers):
    """PATCH /products/{id}/safety-stock with threshold returns 200."""
    product_id = _create_product(client, auth_headers).json["product_id"]
    resp = client.patch(f"{BASE}/products/{product_id}/safety-stock", json={
        "threshold": 5,
    }, headers=auth_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Validation: malformed payloads return 400 with structured error
# ---------------------------------------------------------------------------

def test_create_product_missing_required_fields_400(client, auth_headers):
    """POST /products with empty body returns 400 with validation_error and fields."""
    resp = client.post(f"{BASE}/products", json={}, headers=auth_headers)
    assert resp.status_code == 400
    data = resp.json
    assert data["error"] == "validation_error"
    assert "fields" in data
    for field in ("sku", "name", "brand", "category", "price_usd"):
        assert field in data["fields"], f"Expected '{field}' in validation fields"


def test_create_product_invalid_price_400(client, auth_headers):
    """POST /products with non-numeric price returns 400 with validation_error."""
    resp = client.post(f"{BASE}/products", json={
        "sku": _unique_sku(),
        "name": "Test",
        "brand": "B",
        "category": "C",
        "price_usd": "not_a_number",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"


def test_update_product_invalid_price_400(client, auth_headers):
    """PATCH /products/{id} with negative price returns 400 with validation_error."""
    product_id = _create_product(client, auth_headers).json["product_id"]
    resp = client.patch(f"{BASE}/products/{product_id}", json={
        "price_usd": -10,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
