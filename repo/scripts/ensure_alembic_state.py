"""
Recover SQLite databases that have application tables but no Alembic history.

This happens when tables were created with SQLAlchemy create_all() or an old
workflow never wrote alembic_version. In that case `flask db upgrade` would
re-run 0001 and fail with "table already exists".

Run before `flask db upgrade`: if we detect that state, stamp head so upgrade
becomes a no-op (or applies only newer migrations).
"""
from __future__ import annotations

import os
import sqlite3
import sys

from sqlalchemy.engine.url import make_url

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _sqlite_path() -> str | None:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw or not raw.startswith("sqlite"):
        return None
    url = make_url(raw)
    if url.drivername != "sqlite":
        return None
    db = url.database
    if not db:
        return None
    return db if os.path.isabs(db) else os.path.abspath(os.path.join(_REPO_ROOT, db))


def _needs_stamp(db_path: str) -> bool:
    if not os.path.isfile(db_path) or os.path.getsize(db_path) == 0:
        return False
    conn = sqlite3.connect(db_path)
    try:
        users = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not users:
            return False
        ver_tbl = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if not ver_tbl:
            return True
        row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        return row is None or not row[0]
    finally:
        conn.close()


def main() -> int:
    path = _sqlite_path()
    if not path or not _needs_stamp(path):
        return 0

    print(
        "ensure_alembic_state: found existing tables without Alembic revision; "
        "stamping head (recovery)."
    )
    from app import create_app
    from flask_migrate import stamp

    app = create_app(os.environ.get("FLASK_ENV", "production"))
    with app.app_context():
        stamp(directory="migrations", revision="head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
