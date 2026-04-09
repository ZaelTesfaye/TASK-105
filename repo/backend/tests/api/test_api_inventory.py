"""
API functional tests for inventory management endpoints.

Covers: warehouse and bin CRUD, receipts, issues, transfers, adjustments,
        cycle counts, stock queries (including below safety stock), and transaction listing.
All tests use the Flask test client against /api/v1/warehouses/* and /api/v1/inventory/* endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_sku():
    return f"INV-{uuid.uuid4().hex[:8].upper()}"


def _create_product(client, headers):
    sku = _unique_sku()
    resp = client.post(f"{BASE}/products", json={
        "sku": sku,
        "name": f"Inv Product {uuid.uuid4().hex[:4]}",
        "brand": "InvBrand",
        "category": "Storage",
        "description": "",
        "price_usd": 5.00,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["product_id"]


def _create_warehouse(client, headers, name=None):
    if name is None:
        name = f"WH-{uuid.uuid4().hex[:6]}"
    resp = client.post(f"{BASE}/warehouses", json={
        "name": name,
        "location": "Building A",
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["warehouse_id"]


def _receipt(client, headers, sku_id, warehouse_id, quantity=10, unit_cost=2.50, costing_method="fifo"):
    return client.post(f"{BASE}/inventory/receipts", json={
        "sku_id": sku_id,
        "warehouse_id": warehouse_id,
        "quantity": quantity,
        "unit_cost_usd": unit_cost,
        "costing_method": costing_method,
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=headers)


def _issue(client, headers, sku_id, warehouse_id, quantity):
    return client.post(f"{BASE}/inventory/issues", json={
        "sku_id": sku_id,
        "warehouse_id": warehouse_id,
        "quantity": quantity,
        "occurred_at": "2026-01-02T10:00:00",
    }, headers=headers)


def _get_stock(client, headers, sku_id):
    return client.get(f"{BASE}/inventory/stock?sku_id={sku_id}", headers=headers)


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------

def test_create_warehouse_201(client, auth_headers):
    """POST /warehouses returns 201 with warehouse_id."""
    resp = client.post(f"{BASE}/warehouses", json={
        "name": f"WH-test-{uuid.uuid4().hex[:4]}",
        "location": "Dock A",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert "warehouse_id" in resp.json


def test_create_warehouse_member_403(client, member_headers):
    """Member token POST /warehouses returns 403."""
    resp = client.post(f"{BASE}/warehouses", json={
        "name": f"WH-member-{uuid.uuid4().hex[:4]}",
        "location": "Dock B",
    }, headers=member_headers)
    assert resp.status_code == 403


def test_list_warehouses_200(client, auth_headers):
    """GET /warehouses returns 200 with a list."""
    _create_warehouse(client, auth_headers)
    resp = client.get(f"{BASE}/warehouses", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)


# ---------------------------------------------------------------------------
# Bins
# ---------------------------------------------------------------------------

def test_create_bin_201(client, auth_headers):
    """POST /warehouses/{id}/bins returns 201 with bin_id/bin_code."""
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post(f"{BASE}/warehouses/{wh_id}/bins", json={
        "bin_code": "A1",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert "bin_id" in resp.json
    assert resp.json["bin_code"] == "A1"


def test_list_bins_200(client, auth_headers):
    """GET /warehouses/{id}/bins returns 200 with an array."""
    wh_id = _create_warehouse(client, auth_headers)
    client.post(f"{BASE}/warehouses/{wh_id}/bins", json={"bin_code": "B1"}, headers=auth_headers)
    resp = client.get(f"{BASE}/warehouses/{wh_id}/bins", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)


# ---------------------------------------------------------------------------
# Inventory movements
# ---------------------------------------------------------------------------

def test_receipt_201(client, auth_headers):
    """POST /inventory/receipts returns 201 with transaction_id/type=receipt/quantity_delta/sku_id."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    resp = _receipt(client, auth_headers, sku_id, wh_id, quantity=20)
    assert resp.status_code == 201
    data = resp.json
    assert "transaction_id" in data
    assert data["type"] == "receipt"
    assert data["sku_id"] == sku_id
    assert data["quantity_delta"] == 20


def test_receipt_persists_barcode_serials(client, auth_headers):
    """Receipt accepts barcode / rfid / serial_numbers and returns them on the transaction."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post(f"{BASE}/inventory/receipts", json={
        "sku_id": sku_id,
        "warehouse_id": wh_id,
        "quantity": 3,
        "unit_cost_usd": 1.0,
        "costing_method": "fifo",
        "occurred_at": "2026-01-01T10:00:00",
        "barcode": "BAR-001",
        "rfid": "A1B2C3D4E5F6",
        "serial_numbers": ["SN-1", "SN-2"],
    }, headers=auth_headers)
    assert resp.status_code == 201
    d = resp.json
    assert d["barcode"] == "BAR-001"
    assert d["rfid"] == "A1B2C3D4E5F6"
    assert d["serial_numbers"] == ["SN-1", "SN-2"]


def test_issue_201(client, auth_headers):
    """After receipt, POST /inventory/issues returns 201 with type=issue and on_hand decreases."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=50)

    stock_before = _get_stock(client, auth_headers, sku_id).json
    on_hand_before = stock_before["items"][0]["on_hand_qty"]

    resp = _issue(client, auth_headers, sku_id, wh_id, quantity=10)
    assert resp.status_code == 201
    assert resp.json["type"] == "issue"

    stock_after = _get_stock(client, auth_headers, sku_id).json
    on_hand_after = stock_after["items"][0]["on_hand_qty"]
    assert on_hand_after == on_hand_before - 10


def test_issue_insufficient_stock_422(client, auth_headers):
    """Issuing more than on-hand returns 422 with error=insufficient_stock."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=5)
    resp = _issue(client, auth_headers, sku_id, wh_id, quantity=100)
    assert resp.status_code == 422
    assert resp.json["error"] == "insufficient_stock"


def test_transfer_201(client, auth_headers):
    """POST /inventory/transfers returns 201 with 2 transactions (issue+receipt)."""
    sku_id = _create_product(client, auth_headers)
    wh1 = _create_warehouse(client, auth_headers)
    wh2 = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh1, quantity=30)

    resp = client.post(f"{BASE}/inventory/transfers", json={
        "sku_id": sku_id,
        "from_warehouse_id": wh1,
        "to_warehouse_id": wh2,
        "quantity": 10,
        "occurred_at": "2026-01-03T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 201
    txns = resp.json
    assert isinstance(txns, list)
    assert len(txns) == 2
    types = {t["type"] for t in txns}
    assert types == {"issue", "receipt"}


def test_adjustment_201(client, auth_headers):
    """POST /inventory/adjustments with reason returns 201."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=20)
    resp = client.post(f"{BASE}/inventory/adjustments", json={
        "sku_id": sku_id,
        "warehouse_id": wh_id,
        "quantity_delta": -3,
        "reason": "Damaged items removed",
        "occurred_at": "2026-01-04T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 201


def test_adjustment_no_reason_400(client, auth_headers):
    """POST /inventory/adjustments without reason returns 400 with error=reason_required."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=20)
    resp = client.post(f"{BASE}/inventory/adjustments", json={
        "sku_id": sku_id,
        "warehouse_id": wh_id,
        "quantity_delta": -3,
        "occurred_at": "2026-01-04T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "reason_required"


# ---------------------------------------------------------------------------
# Cycle counts
# ---------------------------------------------------------------------------

def test_cycle_count_201(client, auth_headers):
    """POST /inventory/cycle-counts returns 201 with cycle_count_id and lines."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=10)
    resp = client.post(f"{BASE}/inventory/cycle-counts", json={
        "warehouse_id": wh_id,
        "counted_at": "2026-03-31T12:00:00",
        "lines": [{"sku_id": sku_id, "counted_qty": 10}],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "cycle_count_id" in data
    assert "lines" in data


def test_cycle_count_variance_requires_reason_400(client, auth_headers):
    """Cycle count with variance but no reason returns 400."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=20)
    resp = client.post(f"{BASE}/inventory/cycle-counts", json={
        "warehouse_id": wh_id,
        "counted_at": "2026-03-31T12:00:00",
        "lines": [{"sku_id": sku_id, "counted_qty": 17}],  # variance=-3, no reason
    }, headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Stock queries
# ---------------------------------------------------------------------------

def test_query_stock_200(client, auth_headers):
    """GET /inventory/stock?sku_id={id} returns 200 with items array having on_hand_qty."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=25)
    resp = _get_stock(client, auth_headers, sku_id)
    assert resp.status_code == 200
    data = resp.json
    assert "items" in data
    assert len(data["items"]) >= 1
    assert "on_hand_qty" in data["items"][0]


def test_query_stock_below_safety_200(client, auth_headers):
    """After setting safety stock and issuing below threshold, ?below_safety_stock=true shows the item."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=20)

    # Set safety stock threshold of 15
    client.patch(f"{BASE}/products/{sku_id}/safety-stock", json={"threshold": 15}, headers=auth_headers)

    # Issue enough to go below threshold
    _issue(client, auth_headers, sku_id, wh_id, quantity=10)  # leaves 10, below 15

    resp = client.get(f"{BASE}/inventory/stock?below_safety_stock=true", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json["items"]
    sku_ids = [item["sku_id"] for item in items]
    assert sku_id in sku_ids


# ---------------------------------------------------------------------------
# Transaction listing
# ---------------------------------------------------------------------------

def test_list_transactions_200(client, auth_headers):
    """GET /inventory/transactions returns 200 with paginated results."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=10)
    resp = client.get(f"{BASE}/inventory/transactions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json
    assert "total" in data
    assert "items" in data


def test_list_transactions_type_filter(client, auth_headers):
    """GET /inventory/transactions?type=receipt returns only receipt transactions."""
    sku_id = _create_product(client, auth_headers)
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, quantity=10)

    resp = client.get(f"{BASE}/inventory/transactions?sku_id={sku_id}&type=receipt", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json["items"]
    assert len(items) >= 1
    assert all(t["type"] == "receipt" for t in items)
