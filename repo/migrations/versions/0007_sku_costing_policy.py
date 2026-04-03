"""SKU-level costing method policy table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-02

Adds sku_costing_policies to enforce that every receipt for a given SKU uses
the same costing method across all warehouses.  The first receipt writes the
policy row; subsequent receipts with a different method raise 422.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).scalar()
    return row > 0


def upgrade():
    if not _table_exists("sku_costing_policies"):
        op.create_table(
            "sku_costing_policies",
            sa.Column("sku_id", sa.String(36), sa.ForeignKey("products.product_id"),
                      primary_key=True, nullable=False),
            sa.Column("costing_method", sa.String(32), nullable=False),
            sa.Column("locked_at", sa.DateTime, nullable=False),
        )


def downgrade():
    op.drop_table("sku_costing_policies")
