"""add product search fields

Revision ID: 20260514_0011
Revises: 20260514_0010
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0011"
down_revision: str | None = "20260514_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("article", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("barcode", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("search_keywords", sa.Text(), nullable=True))
    op.create_index(op.f("ix_products_article"), "products", ["article"], unique=False)
    op.create_index(op.f("ix_products_barcode"), "products", ["barcode"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_barcode"), table_name="products")
    op.drop_index(op.f("ix_products_article"), table_name="products")
    op.drop_column("products", "search_keywords")
    op.drop_column("products", "barcode")
    op.drop_column("products", "article")
