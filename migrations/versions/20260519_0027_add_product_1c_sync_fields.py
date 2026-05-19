"""add product 1c sync fields

Revision ID: 20260519_0027
Revises: 20260519_0026
Create Date: 2026-05-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260519_0027"
down_revision: str | None = "20260519_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("sync_status", sa.String(length=50), nullable=True))
    op.add_column(
        "products",
        sa.Column("low_stock_threshold", sa.Numeric(12, 3), server_default="5", nullable=False),
    )
    op.add_column("products", sa.Column("deleted_by", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_products_external_1c_id"), "products", ["external_1c_id"], unique=False)
    op.create_index(op.f("ix_products_sync_status"), "products", ["sync_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_sync_status"), table_name="products")
    op.drop_index(op.f("ix_products_external_1c_id"), table_name="products")
    op.drop_column("products", "deleted_by")
    op.drop_column("products", "low_stock_threshold")
    op.drop_column("products", "sync_status")
    op.drop_column("products", "external_1c_id")
