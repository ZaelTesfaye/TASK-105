"""Warehouse community scoping and inventory identifiers

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-02

- Links warehouses to communities for settlement/report attribution.
- Adds barcode / RFID / serial_numbers (JSON list) on lots and transactions.

SQLite notes:
  - ALTER TABLE ... ADD CONSTRAINT is not supported.  Foreign-key linkage uses
    batch_alter_table (table recreation) instead.
  - All column additions are guarded with column-existence checks so the
    migration is safe to re-run after a partial failure (non-transactional DDL).
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    """Check whether *table* already has *column* (SQLite PRAGMA)."""
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info('{table}')")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade():
    # --- warehouses: add community_id with FK via batch (SQLite-safe) ---
    if not _has_column("warehouses", "community_id"):
        with op.batch_alter_table("warehouses", schema=None) as batch:
            batch.add_column(
                sa.Column("community_id", sa.String(36), nullable=True),
            )
            batch.create_foreign_key(
                "fk_warehouses_community",
                "communities",
                ["community_id"],
                ["community_id"],
            )
    # Index may or may not exist; CREATE INDEX IF NOT EXISTS is SQLite-safe
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_warehouses_community_id "
        "ON warehouses (community_id)"
    )

    # --- inventory_lots: barcode, rfid, serial_numbers ---
    for col_name, col_type in [
        ("barcode", sa.String(128)),
        ("rfid", sa.String(128)),
        ("serial_numbers", sa.Text()),
    ]:
        if not _has_column("inventory_lots", col_name):
            op.add_column("inventory_lots", sa.Column(col_name, col_type, nullable=True))

    # --- inventory_transactions: barcode, rfid, serial_numbers ---
    for col_name, col_type in [
        ("barcode", sa.String(128)),
        ("rfid", sa.String(128)),
        ("serial_numbers", sa.Text()),
    ]:
        if not _has_column("inventory_transactions", col_name):
            op.add_column("inventory_transactions", sa.Column(col_name, col_type, nullable=True))


def downgrade():
    op.drop_column("inventory_transactions", "serial_numbers")
    op.drop_column("inventory_transactions", "rfid")
    op.drop_column("inventory_transactions", "barcode")

    op.drop_column("inventory_lots", "serial_numbers")
    op.drop_column("inventory_lots", "rfid")
    op.drop_column("inventory_lots", "barcode")

    op.execute("DROP INDEX IF EXISTS ix_warehouses_community_id")
    with op.batch_alter_table("warehouses", schema=None) as batch:
        batch.drop_constraint("fk_warehouses_community", type_="foreignkey")
        batch.drop_column("community_id")
