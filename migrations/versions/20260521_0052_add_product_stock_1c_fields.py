"""add product stock 1c fields

Revision ID: 20260521_0052
Revises: 20260521_0051
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0052"
down_revision: str | None = "20260521_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("reserved_quantity", sa.Numeric(12, 3), server_default="0", nullable=False))
    op.add_column("products", sa.Column("stock_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_movements", sa.Column("old_quantity", sa.Numeric(12, 3), nullable=True))
    op.add_column("stock_movements", sa.Column("new_quantity", sa.Numeric(12, 3), nullable=True))
    op.add_column("stock_movements", sa.Column("source", sa.String(length=50), nullable=True))
    op.add_column("stock_movements", sa.Column("warehouse_external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("stock_movements", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_stock_movements_source"), "stock_movements", ["source"], unique=False)
    op.create_index(
        op.f("ix_stock_movements_warehouse_external_1c_id"),
        "stock_movements",
        ["warehouse_external_1c_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_movements_warehouse_external_1c_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_source"), table_name="stock_movements")
    op.drop_column("stock_movements", "created_at")
    op.drop_column("stock_movements", "warehouse_external_1c_id")
    op.drop_column("stock_movements", "source")
    op.drop_column("stock_movements", "new_quantity")
    op.drop_column("stock_movements", "old_quantity")
    op.drop_column("products", "stock_updated_at")
    op.drop_column("products", "reserved_quantity")
