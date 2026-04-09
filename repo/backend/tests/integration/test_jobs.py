"""
Background job tests.
Covers: safety stock alerts, slow-moving flags, attachment cleanup,
        message redelivery (purge + backoff), trending precompute.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Safety stock
# ---------------------------------------------------------------------------

def test_job_logs_include_correlation_id(client, auth_headers, caplog):
    """Job log records must include a correlation_id field."""
    import json as _json
    import logging
    from app.jobs.message_redelivery import redeliver_messages

    with client.application.app_context():
        with caplog.at_level(logging.DEBUG, logger="app.jobs.message_redelivery"):
            redeliver_messages()

    # At least the "redelivery_run" summary log should be emitted
    found_cid = False
    for record in caplog.records:
        try:
            data = _json.loads(record.getMessage())
            if "correlation_id" in data and data["correlation_id"]:
                found_cid = True
                assert data["correlation_id"].startswith("job-")
                break
        except (ValueError, TypeError):
            continue
    assert found_cid, "No log record with a non-empty correlation_id was emitted by the job"


def test_safety_stock_creates_ticket(client, auth_headers):
    """Lot below threshold → AdminTicket created."""
    from app.jobs.safety_stock import check_safety_stock
    from app.models.admin import AdminTicket
    from app.models.inventory import InventoryLot
    from app.extensions import db

    wh_id = client.post("/api/v1/warehouses",
                        json={"name": "WH-SS", "location": "A"},
                        headers=auth_headers).json["warehouse_id"]
    prod_id = client.post("/api/v1/products", json={
        "sku": f"SS-{uuid.uuid4().hex[:6]}", "name": "SafetyProd",
        "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers).json["product_id"]

    # Receipt 5 units
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": prod_id, "warehouse_id": wh_id, "quantity": 5,
    }, headers=auth_headers)

    with client.application.app_context():
        # Set safety_stock_threshold on the lot directly (no REST endpoint for this)
        lot = InventoryLot.query.filter_by(sku_id=prod_id, warehouse_id=wh_id).first()
        lot.safety_stock_threshold = 10  # on_hand=5 < threshold=10
        db.session.commit()

        before = AdminTicket.query.filter(
            AdminTicket.target_type == "inventory_lot",
            AdminTicket.status == "open",
        ).count()
        check_safety_stock()
        after = AdminTicket.query.filter(
            AdminTicket.target_type == "inventory_lot",
            AdminTicket.status == "open",
        ).count()

    assert after > before


def test_safety_stock_no_duplicate_ticket(client, auth_headers):
    """Running the job twice doesn't create duplicate open tickets."""
    from app.jobs.safety_stock import check_safety_stock
    from app.models.admin import AdminTicket
    from app.models.inventory import InventoryLot
    from app.extensions import db

    wh_id = client.post("/api/v1/warehouses",
                        json={"name": "WH-SS2", "location": "B"},
                        headers=auth_headers).json["warehouse_id"]
    prod_id = client.post("/api/v1/products", json={
        "sku": f"SS2-{uuid.uuid4().hex[:6]}", "name": "SafetyProd2",
        "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers).json["product_id"]
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": prod_id, "warehouse_id": wh_id, "quantity": 1,
    }, headers=auth_headers)

    with client.application.app_context():
        lot = InventoryLot.query.filter_by(sku_id=prod_id, warehouse_id=wh_id).first()
        lot.safety_stock_threshold = 100  # on_hand=1 < threshold=100
        db.session.commit()

        subject = f"Safety stock alert: SKU {prod_id}"
        check_safety_stock()
        count_after_first = AdminTicket.query.filter_by(subject=subject, status="open").count()
        check_safety_stock()
        count_after_second = AdminTicket.query.filter_by(subject=subject, status="open").count()

    assert count_after_first == count_after_second == 1


# ---------------------------------------------------------------------------
# Slow-moving
# ---------------------------------------------------------------------------

def test_slow_moving_flags_old_lot(client, auth_headers):
    """Lot with no issue for 61+ days → slow_moving=True."""
    from app.jobs.slow_moving import flag_slow_moving
    from app.models.inventory import InventoryLot
    from app.extensions import db

    wh_id = client.post("/api/v1/warehouses",
                        json={"name": "WH-SM", "location": "C"},
                        headers=auth_headers).json["warehouse_id"]
    prod_id = client.post("/api/v1/products", json={
        "sku": f"SM-{uuid.uuid4().hex[:6]}", "name": "SlowProd",
        "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers).json["product_id"]
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": prod_id, "warehouse_id": wh_id, "quantity": 10,
    }, headers=auth_headers)

    with client.application.app_context():
        # Backdate the lot's created_at and last_issue_at to 61 days ago
        lot = InventoryLot.query.filter_by(
            sku_id=prod_id, warehouse_id=wh_id
        ).first()
        old_date = datetime.now(timezone.utc) - timedelta(days=61)
        lot.created_at = old_date
        lot.last_issue_at = None
        db.session.commit()

        flag_slow_moving()

        db.session.expire(lot)
        assert lot.slow_moving is True


def test_slow_moving_recent_issue_not_flagged(client, auth_headers):
    """Lot issued yesterday → NOT flagged as slow-moving."""
    from app.jobs.slow_moving import flag_slow_moving
    from app.models.inventory import InventoryLot
    from app.extensions import db

    wh_id = client.post("/api/v1/warehouses",
                        json={"name": "WH-SM2", "location": "D"},
                        headers=auth_headers).json["warehouse_id"]
    prod_id = client.post("/api/v1/products", json={
        "sku": f"SM2-{uuid.uuid4().hex[:6]}", "name": "ActiveProd",
        "brand": "B", "category": "C", "price_usd": 1.0,
    }, headers=auth_headers).json["product_id"]
    client.post("/api/v1/inventory/receipts", json={
        "sku_id": prod_id, "warehouse_id": wh_id, "quantity": 10,
    }, headers=auth_headers)
    client.post("/api/v1/inventory/issues", json={
        "sku_id": prod_id, "warehouse_id": wh_id, "quantity": 1,
    }, headers=auth_headers)

    with client.application.app_context():
        lot = InventoryLot.query.filter_by(
            sku_id=prod_id, warehouse_id=wh_id
        ).first()
        # last_issue_at is today (just issued), so should not be flagged
        flag_slow_moving()
        db.session.expire(lot)
        assert lot.slow_moving is False


# ---------------------------------------------------------------------------
# Attachment cleanup
# ---------------------------------------------------------------------------

def test_attachment_cleanup_removes_soft_deleted(client, auth_headers, tmp_path):
    """Soft-deleted attachment DB row is hard-deleted; file removed from disk."""
    from app.jobs.attachment_cleanup import cleanup_attachments
    from app.models.content import Attachment
    from app.extensions import db
    import io

    # Create a content item
    content_id = client.post("/api/v1/content", json={
        "type": "article", "title": "Cleanup Test", "body": "body",
    }, headers=auth_headers).json["content_id"]

    # Upload a real file (use test client multipart)
    data = b"hello world"
    resp = client.post(
        f"/api/v1/content/{content_id}/attachments",
        data={"file": (io.BytesIO(data), "test.txt", "text/plain")},
        headers=auth_headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    att_id = resp.json["attachment_id"]

    with client.application.app_context():
        att = db.session.get(Attachment, att_id)
        local_path = att.local_path
        # Write the file to disk so cleanup can remove it
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)

        # Soft-delete via route
        del_resp = client.delete(
            f"/api/v1/content/{content_id}/attachments/{att_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204

        # Run cleanup
        cleanup_attachments()

        # Row should be hard-deleted from DB
        assert db.session.get(Attachment, att_id) is None


def test_attachment_cleanup_orphan_removal(client, auth_headers, tmp_path):
    """Orphaned files on disk (not in DB) are removed by cleanup job."""
    from app.jobs.attachment_cleanup import cleanup_attachments
    from flask import current_app

    with client.application.app_context():
        attach_dir = current_app.config.get("ATTACHMENT_DIR", "data/attachments")
        os.makedirs(attach_dir, exist_ok=True)
        orphan = os.path.join(attach_dir, "orphan_test_file.txt")
        with open(orphan, "w") as f:
            f.write("orphan")

        cleanup_attachments()

        assert not os.path.exists(orphan)


# ---------------------------------------------------------------------------
# Message redelivery
# ---------------------------------------------------------------------------

def _make_user(client):
    username = f"u_{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/auth/register", json={
        "username": username, "password": "ValidPass1234!", "role": "Member",
    })
    user_id = reg.json["user_id"]
    token = client.post("/api/v1/auth/login", json={
        "username": username, "password": "ValidPass1234!",
    }).json["token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def test_redelivery_purges_expired(client, auth_headers):
    """Messages past 7-day TTL are hard-deleted by the redelivery job."""
    from app.jobs.message_redelivery import redeliver_messages
    from app.models.messaging import Message
    from app.extensions import db

    recip_id, _ = _make_user(client)
    client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "Expire me",
    }, headers=auth_headers)

    with client.application.app_context():
        # Backdate expires_at to past
        msg = Message.query.order_by(Message.sent_at.desc()).first()
        msg.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        mid = msg.message_id

        redeliver_messages()

        assert db.session.get(Message, mid) is None


def test_redelivery_backoff_respected(client, auth_headers):
    """Receipt with future next_retry_at is skipped during redelivery."""
    from app.jobs.message_redelivery import redeliver_messages
    from app.models.messaging import Message, MessageReceipt
    from app.extensions import db

    recip_id, _ = _make_user(client)
    client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "Backoff",
    }, headers=auth_headers)

    with client.application.app_context():
        msg = Message.query.order_by(Message.sent_at.desc()).first()
        receipt = MessageReceipt.query.filter_by(
            message_id=msg.message_id, status="sent"
        ).first()
        # Set next_retry_at far in the future
        receipt.next_retry_at = datetime.now(timezone.utc) + timedelta(hours=24)
        receipt.retry_count = 5
        db.session.commit()

        # Run redelivery — this receipt should be skipped
        redeliver_messages()

        db.session.expire(receipt)
        # retry_count should remain 5 (not incremented — was skipped)
        assert receipt.retry_count == 5


def test_redelivery_increments_retry_count(client, auth_headers):
    """Attempted delivery increments retry_count and sets next_retry_at."""
    from app.jobs.message_redelivery import redeliver_messages
    from app.models.messaging import Message, MessageReceipt
    from app.extensions import db

    recip_id, _ = _make_user(client)
    client.post("/api/v1/messages", json={
        "type": "text", "recipient_id": recip_id, "body": "Retry count",
    }, headers=auth_headers)

    with client.application.app_context():
        msg = Message.query.order_by(Message.sent_at.desc()).first()
        receipt = MessageReceipt.query.filter_by(
            message_id=msg.message_id, status="sent"
        ).first()
        assert receipt.retry_count == 0
        assert receipt.next_retry_at is None

        redeliver_messages()

        db.session.expire(receipt)
        assert receipt.retry_count == 1
        assert receipt.next_retry_at is not None
        # next_retry_at should be in the future (at least 60s from now)
        assert receipt.next_retry_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Trending precompute
# ---------------------------------------------------------------------------

def test_trending_precompute(client, auth_headers):
    """Searching a term multiple times makes it appear in trending cache."""
    from app.jobs.trending_precompute import precompute_trending
    from app.models.catalog import TrendingCache
    from app.extensions import db

    # Register a member to use search
    _, user_headers = _make_user(client)

    # Create a product so search works
    client.post("/api/v1/products", json={
        "sku": f"TR-{uuid.uuid4().hex[:6]}", "name": "TrendProd",
        "brand": "TrendBrand", "category": "Electronics", "price_usd": 9.99,
    }, headers=auth_headers)

    # Search for the term several times via search_products (which logs queries)
    for _ in range(3):
        client.get("/api/v1/search/products?q=TrendProd", headers=user_headers)

    with client.application.app_context():
        precompute_trending()
        cached = db.session.query(TrendingCache).filter(
            TrendingCache.term.ilike("%trendprod%")
        ).first()
        assert cached is not None
        assert cached.score > 0
