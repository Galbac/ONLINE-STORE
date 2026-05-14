"""add product catalog fields

Revision ID: 20260514_0009
Revises: 20260514_0008
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0009"
down_revision: str | None = "20260514_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("slug", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("preview_image_url", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("product_type", sa.String(length=20), server_default="piece", nullable=False))
    op.add_column("products", sa.Column("old_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("products", sa.Column("popularity", sa.Integer(), server_default="0", nullable=False))
    op.add_column("products", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("products", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE products SET slug = CONCAT('product-', id) WHERE slug IS NULL")
    op.alter_column("products", "slug", existing_type=sa.String(length=255), nullable=False)
    op.create_index(op.f("ix_products_slug"), "products", ["slug"], unique=True)
    op.create_index(op.f("ix_products_is_active"), "products", ["is_active"], unique=False)
    op.create_index(op.f("ix_products_is_deleted"), "products", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_products_is_available"), "products", ["is_available"], unique=False)
    op.create_index(op.f("ix_products_price"), "products", ["price"], unique=False)
    op.create_index(op.f("ix_products_product_type"), "products", ["product_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_product_type"), table_name="products")
    op.drop_index(op.f("ix_products_price"), table_name="products")
    op.drop_index(op.f("ix_products_is_available"), table_name="products")
    op.drop_index(op.f("ix_products_is_deleted"), table_name="products")
    op.drop_index(op.f("ix_products_is_active"), table_name="products")
    op.drop_index(op.f("ix_products_slug"), table_name="products")
    op.drop_column("products", "deleted_at")
    op.drop_column("products", "is_deleted")
    op.drop_column("products", "popularity")
    op.drop_column("products", "old_price")
    op.drop_column("products", "product_type")
    op.drop_column("products", "preview_image_url")
    op.drop_column("products", "slug")
