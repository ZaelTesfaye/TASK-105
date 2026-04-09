"""
Migration-path tests -- validate the Alembic upgrade chain against a real
temporary SQLite database file (NOT db.create_all()).

These tests ensure that:
  1. A fresh DB can be upgraded from empty to head without errors.
  2. Key schema objects created by migrations 0001-0007 exist.
  3. Running upgrade a second time is a no-op success (idempotency).

Each test creates a minimal Flask app with a temp file-backed SQLite URI
and calls ``flask db upgrade`` through Flask-Migrate.  The session-scoped
``app`` fixture from conftest.py is NOT used.
"""
import os
import sqlite3

import pytest

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, upgrade as fm_upgrade


@pytest.fixture()
def mig_db(tmp_path):
    """
    Yield (app, db_path) for a fresh temp SQLite file.
    Builds a minimal Flask app with its own SQLAlchemy + Migrate extensions
    so the session-scoped app from conftest.py is never touched.
    """
    db_path = str(tmp_path / "test_mig.sqlite3")
    db_uri = f"sqlite:///{db_path}"

    # Minimal Flask app — just enough for Migrate to work
    _app = Flask(__name__)
    _app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    _app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    _app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
    }

    _db = SQLAlchemy(_app)
    _mig = Migrate(_app, _db)

    yield _app, db_path

    # Dispose engine to release Windows file locks
    with _app.app_context():
        _db.engine.dispose()


def _upgrade(app, revision="head"):
    with app.app_context():
        fm_upgrade(revision=revision)


# -----------------------------------------------------------------------
# 1. Fresh DB -> head succeeds
# -----------------------------------------------------------------------

def test_fresh_db_upgrade_to_head(mig_db):
    app, db_path = mig_db
    _upgrade(app, "head")
    conn = sqlite3.connect(db_path)
    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    conn.close()
    assert ver is not None
    assert ver[0] == "0007"


# -----------------------------------------------------------------------
# 2. Key schema objects exist at head
# -----------------------------------------------------------------------

def test_schema_objects_at_head(mig_db):
    app, db_path = mig_db
    _upgrade(app, "head")

    conn = sqlite3.connect(db_path)

    def cols(table):
        return {r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}

    def table_exists(table):
        r = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return r[0] > 0

    # Migration 0001 tables
    assert table_exists("users")
    assert table_exists("communities")
    assert table_exists("warehouses")
    assert table_exists("inventory_lots")
    assert table_exists("audit_log")

    # Migration 0004
    assert table_exists("community_members")

    # Migration 0006: warehouse community_id + inventory identifiers
    wh_cols = cols("warehouses")
    assert "community_id" in wh_cols, f"community_id missing: {wh_cols}"

    lot_cols = cols("inventory_lots")
    assert "barcode" in lot_cols
    assert "rfid" in lot_cols
    assert "serial_numbers" in lot_cols

    txn_cols = cols("inventory_transactions")
    assert "barcode" in txn_cols
    assert "rfid" in txn_cols
    assert "serial_numbers" in txn_cols

    # Migration 0007: sku_costing_policies
    assert table_exists("sku_costing_policies")
    scp_cols = cols("sku_costing_policies")
    assert "sku_id" in scp_cols
    assert "costing_method" in scp_cols
    assert "locked_at" in scp_cols

    # Migration 0003: message_receipts retry columns
    mr_cols = cols("message_receipts")
    assert "retry_count" in mr_cols
    assert "next_retry_at" in mr_cols

    conn.close()


# -----------------------------------------------------------------------
# 3. Second upgrade is a no-op success
# -----------------------------------------------------------------------

def test_upgrade_idempotent(mig_db):
    app, db_path = mig_db
    _upgrade(app, "head")
    # Second run must succeed without error
    _upgrade(app, "head")
    conn = sqlite3.connect(db_path)
    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    conn.close()
    assert ver[0] == "0007"
