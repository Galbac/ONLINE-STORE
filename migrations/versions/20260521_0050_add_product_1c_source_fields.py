"""add product 1c source fields

Revision ID: 20260521_0050
Revises: 20260521_0049
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0050"
down_revision: str | None = "20260521_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("source", sa.String(length=50), nullable=True))
    op.create_index(op.f("ix_products_source"), "products", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_source"), table_name="products")
    op.drop_column("products", "source")
    op.drop_column("products", "last_sync_at")
