"""Inventory endpoint tests — warehouses, bins, movements, costing, cycle counts."""


def _create_product(client, headers, sku="INV-SKU-001"):
    resp = client.post("/api/v1/products", json={
        "sku": sku, "name": "Test Product", "brand": "Brand", "category": "Cat",
        "description": "", "price_usd": 5.00,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["product_id"]


def _create_warehouse(client, headers, name="Main WH"):
    resp = client.post("/api/v1/warehouses", json={"name": name, "location": "Building A"},
                       headers=headers)
    assert resp.status_code == 201
    return resp.json["warehouse_id"]


def _receipt(client, headers, sku_id, wh_id, qty, cost=2.50, method="fifo", sku_suffix=""):
    return client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": qty,
        "costing_method": method, "unit_cost_usd": cost,
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=headers)


def _issue(client, headers, sku_id, wh_id, qty):
    return client.post("/api/v1/inventory/issues", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": qty,
        "occurred_at": "2026-01-02T10:00:00",
    }, headers=headers)


def _stock(client, headers, sku_id):
    return client.get(f"/api/v1/inventory/stock?sku_id={sku_id}", headers=headers)


# ---------------------------------------------------------------------------
# Warehouse & bin
# ---------------------------------------------------------------------------

def test_create_warehouse(client, auth_headers):
    resp = client.post("/api/v1/warehouses", json={"name": "WH-1", "location": "Dock A"},
                       headers=auth_headers)
    assert resp.status_code == 201
    assert "warehouse_id" in resp.json


def test_list_warehouses(client, auth_headers):
    _create_warehouse(client, auth_headers, name="ListWH")
    resp = client.get("/api/v1/warehouses", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json, list)


def test_create_bin(client, auth_headers):
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post(f"/api/v1/warehouses/{wh_id}/bins",
                       json={"bin_code": "A1"}, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["bin_code"] == "A1"


def test_list_bins(client, auth_headers):
    wh_id = _create_warehouse(client, auth_headers)
    client.post(f"/api/v1/warehouses/{wh_id}/bins",
                json={"bin_code": "B1"}, headers=auth_headers)
    resp = client.get(f"/api/v1/warehouses/{wh_id}/bins", headers=auth_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Receipt + stock query
# ---------------------------------------------------------------------------

def test_receipt_and_stock(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-REC-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    resp = _receipt(client, auth_headers, sku_id, wh_id, qty=50, cost=2.50)
    assert resp.status_code == 201
    assert resp.json["type"] == "receipt"

    stock = _stock(client, auth_headers, sku_id).json
    assert stock["items"][0]["on_hand_qty"] == 50


def test_stock_response_includes_current_cost(client, auth_headers):
    """GET /inventory/stock must include current_cost_usd per api-spec."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-COST-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10, cost=5.00)

    stock = _stock(client, auth_headers, sku_id).json
    item = stock["items"][0]
    assert "current_cost_usd" in item
    assert item["current_cost_usd"] == 5.0


# ---------------------------------------------------------------------------
# Adjustment
# ---------------------------------------------------------------------------

def test_adjustment_requires_reason(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-ADJ-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)
    resp = client.post("/api/v1/inventory/adjustments", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity_delta": -3,
        "occurred_at": "2026-03-31T11:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "reason_required"


def test_adjustment_with_reason_creates_audit_log(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-AADJ-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)
    resp = client.post("/api/v1/inventory/adjustments", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity_delta": -2,
        "reason": "Shrinkage", "occurred_at": "2026-03-31T11:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert "audit_log_id" in resp.json
    assert resp.json["transaction"]["quantity_delta"] == -2


# ---------------------------------------------------------------------------
# FIFO cost layer consumption on issue
# ---------------------------------------------------------------------------

def test_fifo_cost_layers_consumed_on_issue(client, auth_headers):
    """
    Issue must consume FIFO layers oldest-first.
    After receipt of 10@$5 then 5@$8, issuing 8 should leave:
      layer1: 2 remaining at $5
      layer2: 5 remaining at $8
    Weighted avg cost = (2*5 + 5*8) / 7 ≈ 7.14
    """
    import uuid, math
    sku_id = _create_product(client, auth_headers, f"INV-FIFO-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)

    # Receipt 1: 10 units @ $5
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 10,
        "costing_method": "fifo", "unit_cost_usd": 5.0,
        "occurred_at": "2026-01-01T08:00:00",
    }, headers=auth_headers)
    # Receipt 2: 5 units @ $8
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 5,
        "costing_method": "fifo", "unit_cost_usd": 8.0,
        "occurred_at": "2026-01-01T09:00:00",
    }, headers=auth_headers)

    # Issue 8 units — should consume all of layer1 (10) partially (8), leaving 2 in layer1
    _issue(client, auth_headers, sku_id, wh_id, qty=8)

    stock = _stock(client, auth_headers, sku_id).json
    item = stock["items"][0]
    assert item["on_hand_qty"] == 7  # 15 - 8

    # Weighted avg cost of remaining (2@$5 + 5@$8) / 7
    expected_cost = (2 * 5.0 + 5 * 8.0) / 7
    assert math.isclose(item["current_cost_usd"], expected_cost, rel_tol=1e-4)


def test_fifo_full_layer_consumption(client, auth_headers):
    """Issuing exactly the first layer quantity should zero that layer."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-FFULL-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=5, cost=3.0)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10, cost=6.0)

    # Issue exactly 5 — consumes first layer entirely
    _issue(client, auth_headers, sku_id, wh_id, qty=5)

    stock = _stock(client, auth_headers, sku_id).json
    item = stock["items"][0]
    assert item["on_hand_qty"] == 10
    # Only second layer remains at $6
    assert item["current_cost_usd"] == 6.0


# ---------------------------------------------------------------------------
# Issue resets slow-moving flag
# ---------------------------------------------------------------------------

def test_issue_resets_slow_moving_flag(client, auth_headers):
    """An issue operation must clear the slow_moving flag on the lot."""
    import uuid
    from app.models.inventory import InventoryLot
    from datetime import datetime, timezone, timedelta

    sku_id = _create_product(client, auth_headers, f"INV-SM-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=20)

    # Manually mark lot as slow-moving
    with client.application.app_context():
        lot = InventoryLot.query.filter_by(sku_id=sku_id, warehouse_id=wh_id).first()
        lot.slow_moving = True
        from app.extensions import db
        db.session.commit()

    # Verify it shows as slow-moving in stock query
    stock_before = _stock(client, auth_headers, sku_id).json
    assert stock_before["items"][0]["slow_moving"] is True

    # Issue 1 unit — should reset slow_moving
    _issue(client, auth_headers, sku_id, wh_id, qty=1)

    stock_after = _stock(client, auth_headers, sku_id).json
    assert stock_after["items"][0]["slow_moving"] is False


# ---------------------------------------------------------------------------
# Costing method immutability
# ---------------------------------------------------------------------------

def test_costing_method_locked_after_first_transaction(client, auth_headers):
    """Attempting to change costing_method on an existing lot must return 422."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-LOCK-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)

    # First receipt establishes costing method as "fifo"
    _receipt(client, auth_headers, sku_id, wh_id, qty=10, method="fifo")

    # Second receipt with different costing_method should fail
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 5,
        "costing_method": "moving_average", "unit_cost_usd": 3.0,
        "occurred_at": "2026-01-02T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json["error"] == "costing_method_locked"


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

def test_transfer_between_warehouses(client, auth_headers):
    """Transfer creates an issue + receipt pair."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-XFER-{uuid.uuid4().hex[:6]}")
    wh1 = _create_warehouse(client, auth_headers, name=f"WH-src-{uuid.uuid4().hex[:4]}")
    wh2 = _create_warehouse(client, auth_headers, name=f"WH-dst-{uuid.uuid4().hex[:4]}")

    _receipt(client, auth_headers, sku_id, wh1, qty=20)

    resp = client.post("/api/v1/inventory/transfers", json={
        "sku_id": sku_id,
        "from_warehouse_id": wh1, "to_warehouse_id": wh2,
        "quantity": 8,
        "occurred_at": "2026-01-03T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 201
    txns = resp.json
    assert len(txns) == 2
    types = {t["type"] for t in txns}
    assert types == {"issue", "receipt"}

    # Source should have 12, destination 8
    src = _stock(client, auth_headers, sku_id).json
    by_wh = {item["warehouse_id"]: item["on_hand_qty"] for item in src["items"]}
    assert by_wh[wh1] == 12
    assert by_wh[wh2] == 8


def test_transfer_inherits_costing_method(client, auth_headers):
    """Destination lot must inherit source lot's costing method."""
    import uuid
    from app.models.inventory import InventoryLot
    sku_id = _create_product(client, auth_headers, f"INV-XCOS-{uuid.uuid4().hex[:6]}")
    wh1 = _create_warehouse(client, auth_headers, name=f"WH-xsrc-{uuid.uuid4().hex[:4]}")
    wh2 = _create_warehouse(client, auth_headers, name=f"WH-xdst-{uuid.uuid4().hex[:4]}")

    # Source is moving_average
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh1, "quantity": 20,
        "costing_method": "moving_average", "unit_cost_usd": 4.0,
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=auth_headers)

    client.post("/api/v1/inventory/transfers", json={
        "sku_id": sku_id,
        "from_warehouse_id": wh1, "to_warehouse_id": wh2,
        "quantity": 5,
    }, headers=auth_headers)

    with client.application.app_context():
        dst_lot = InventoryLot.query.filter_by(sku_id=sku_id, warehouse_id=wh2).first()
        assert dst_lot is not None
        assert dst_lot.costing_method == "moving_average"


# ---------------------------------------------------------------------------
# Cycle count
# ---------------------------------------------------------------------------

def test_cycle_count_variance_requires_reason(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-CC-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=20)

    resp = client.post("/api/v1/inventory/cycle-counts", json={
        "warehouse_id": wh_id,
        "counted_at": "2026-03-31T12:00:00",
        "lines": [{"sku_id": sku_id, "counted_qty": 17}],  # variance=-3, no reason
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "variance_reason_required"


def test_cycle_count_no_variance(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-CCZ-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)

    resp = client.post("/api/v1/inventory/cycle-counts", json={
        "warehouse_id": wh_id,
        "counted_at": "2026-03-31T12:00:00",
        "lines": [{"sku_id": sku_id, "counted_qty": 10}],  # no variance — no reason needed
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["lines"][0]["variance"] == 0


def test_cycle_count_with_variance_and_reason(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-CCV-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)

    resp = client.post("/api/v1/inventory/cycle-counts", json={
        "warehouse_id": wh_id,
        "counted_at": "2026-03-31T12:00:00",
        "lines": [{"sku_id": sku_id, "counted_qty": 8,
                   "variance_reason": "Damaged items removed"}],
    }, headers=auth_headers)
    assert resp.status_code == 201
    line = resp.json["lines"][0]
    assert line["variance"] == -2
    assert line["variance_reason"] == "Damaged items removed"


# ---------------------------------------------------------------------------
# Insufficient stock
# ---------------------------------------------------------------------------

def test_issue_insufficient_stock(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-INSUF-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=5)
    resp = _issue(client, auth_headers, sku_id, wh_id, qty=10)
    assert resp.status_code == 422
    assert resp.json["error"] == "insufficient_stock"


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------

def test_list_transactions(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-TXN-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)
    _issue(client, auth_headers, sku_id, wh_id, qty=3)

    resp = client.get(f"/api/v1/inventory/transactions?sku_id={sku_id}",
                      headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["total"] == 2
    types = {t["type"] for t in resp.json["items"]}
    assert "receipt" in types
    assert "issue" in types


def test_list_transactions_type_filter(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"INV-TXNF-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)

    resp = client.get(f"/api/v1/inventory/transactions?sku_id={sku_id}&type=receipt",
                      headers=auth_headers)
    assert resp.status_code == 200
    assert all(t["type"] == "receipt" for t in resp.json["items"])


# ---------------------------------------------------------------------------
# SKU-level costing method immutability
# ---------------------------------------------------------------------------

def test_sku_costing_policy_locks_on_first_receipt(client, auth_headers):
    """First receipt for a SKU sets the costing method policy."""
    import uuid
    from app.models.inventory import SkuCostingPolicy
    sku_id = _create_product(client, auth_headers, f"SKU-LOCK-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    resp = _receipt(client, auth_headers, sku_id, wh_id, qty=10, method="fifo")
    assert resp.status_code == 201
    with client.application.app_context():
        policy = SkuCostingPolicy.query.get(sku_id)
        assert policy is not None
        assert policy.costing_method == "fifo"


def test_sku_costing_policy_blocks_different_method(client, auth_headers):
    """Second receipt with a different costing method → 422 costing_method_locked."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"SKU-BLK-{uuid.uuid4().hex[:6]}")
    wh1 = _create_warehouse(client, auth_headers, name=f"WH-A-{uuid.uuid4().hex[:4]}")
    wh2 = _create_warehouse(client, auth_headers, name=f"WH-B-{uuid.uuid4().hex[:4]}")
    # First receipt with fifo
    r1 = _receipt(client, auth_headers, sku_id, wh1, qty=10, method="fifo")
    assert r1.status_code == 201
    # Second receipt for same SKU in a different warehouse with moving_average → blocked
    r2 = _receipt(client, auth_headers, sku_id, wh2, qty=5, method="moving_average")
    assert r2.status_code == 422
    assert r2.json["error"] == "costing_method_locked"


def test_sku_costing_same_method_allowed(client, auth_headers):
    """Second receipt for same SKU with same method succeeds."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"SKU-SAME-{uuid.uuid4().hex[:6]}")
    wh1 = _create_warehouse(client, auth_headers, name=f"WH-C-{uuid.uuid4().hex[:4]}")
    wh2 = _create_warehouse(client, auth_headers, name=f"WH-D-{uuid.uuid4().hex[:4]}")
    r1 = _receipt(client, auth_headers, sku_id, wh1, qty=10, method="fifo")
    assert r1.status_code == 201
    r2 = _receipt(client, auth_headers, sku_id, wh2, qty=5, method="fifo")
    assert r2.status_code == 201


# ---------------------------------------------------------------------------
# Barcode / RFID format validation (Fix 4)
# ---------------------------------------------------------------------------

def test_receipt_valid_barcode_accepted(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"BC-OK-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 5,
        "costing_method": "fifo", "unit_cost_usd": 1.0,
        "barcode": "UPC-12345678",
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 201


def test_receipt_invalid_barcode_rejected(client, auth_headers):
    """Barcode with spaces/special chars must be rejected."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"BC-BAD-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 5,
        "costing_method": "fifo", "unit_cost_usd": 1.0,
        "barcode": "INVALID BARCODE!@#",
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_barcode_format"


def test_receipt_invalid_rfid_rejected(client, auth_headers):
    """RFID must be hex only; non-hex chars are rejected."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"RF-BAD-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 5,
        "costing_method": "fifo", "unit_cost_usd": 1.0,
        "rfid": "NOT-HEX-VALUE",
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rfid_format"


def test_receipt_valid_rfid_accepted(client, auth_headers):
    import uuid
    sku_id = _create_product(client, auth_headers, f"RF-OK-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 5,
        "costing_method": "fifo", "unit_cost_usd": 1.0,
        "rfid": "E200001234ABCDEF",
        "occurred_at": "2026-01-01T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 201


def test_issue_invalid_barcode_rejected(client, auth_headers):
    """Issue with invalid barcode format is rejected."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"BC-ISS-{uuid.uuid4().hex[:6]}")
    wh_id = _create_warehouse(client, auth_headers)
    _receipt(client, auth_headers, sku_id, wh_id, qty=10)
    resp = client.post("/api/v1/inventory/issues", json={
        "sku_id": sku_id, "warehouse_id": wh_id, "quantity": 1,
        "barcode": "BAD BARCODE!!",
        "occurred_at": "2026-01-02T10:00:00",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_barcode_format"


def test_transfer_invalid_rfid_rejected(client, auth_headers):
    """Transfer with invalid RFID format is rejected."""
    import uuid
    sku_id = _create_product(client, auth_headers, f"RF-XFR-{uuid.uuid4().hex[:6]}")
    wh1 = _create_warehouse(client, auth_headers, name=f"WH-rfx-{uuid.uuid4().hex[:4]}")
    wh2 = _create_warehouse(client, auth_headers, name=f"WH-rfy-{uuid.uuid4().hex[:4]}")
    _receipt(client, auth_headers, sku_id, wh1, qty=10)
    resp = client.post("/api/v1/inventory/transfers", json={
        "sku_id": sku_id,
        "from_warehouse_id": wh1, "to_warehouse_id": wh2,
        "quantity": 5,
        "rfid": "ZZZZ-NOT-HEX",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rfid_format"


# ---------------------------------------------------------------------------
# Schema validation (Fix 5) — missing/invalid fields return 400/422
# ---------------------------------------------------------------------------

def test_receipt_missing_sku_id_returns_400(client, auth_headers):
    """Missing required field sku_id returns structured validation error."""
    resp = client.post("/api/v1/inventory/receipts", json={
        "warehouse_id": "some-wh", "quantity": 5,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "sku_id" in resp.json["fields"]


def test_receipt_missing_warehouse_id_returns_400(client, auth_headers):
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": "some-sku", "quantity": 5,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "warehouse_id" in resp.json["fields"]


def test_receipt_invalid_quantity_returns_400(client, auth_headers):
    """quantity must be a positive integer."""
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": "x", "warehouse_id": "y", "quantity": -1,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "quantity" in resp.json["fields"]


def test_issue_missing_fields_returns_400(client, auth_headers):
    resp = client.post("/api/v1/inventory/issues", json={}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "sku_id" in resp.json["fields"]
    assert "warehouse_id" in resp.json["fields"]
    assert "quantity" in resp.json["fields"]


def test_transfer_missing_fields_returns_400(client, auth_headers):
    resp = client.post("/api/v1/inventory/transfers", json={}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "sku_id" in resp.json["fields"]
    assert "from_warehouse_id" in resp.json["fields"]
    assert "to_warehouse_id" in resp.json["fields"]


def test_adjustment_missing_fields_returns_400(client, auth_headers):
    resp = client.post("/api/v1/inventory/adjustments", json={}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "sku_id" in resp.json["fields"]


def test_warehouse_missing_name_returns_400(client, auth_headers):
    resp = client.post("/api/v1/warehouses", json={"location": "Bldg A"},
                       headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "name" in resp.json["fields"]


def test_receipt_invalid_costing_method_returns_400(client, auth_headers):
    resp = client.post("/api/v1/inventory/receipts", json={
        "sku_id": "x", "warehouse_id": "y", "quantity": 1,
        "costing_method": "invalid_method",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json["error"] == "validation_error"
    assert "costing_method" in resp.json["fields"]
