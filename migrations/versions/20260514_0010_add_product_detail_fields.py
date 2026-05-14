"""add product detail fields

Revision ID: 20260514_0010
Revises: 20260514_0009
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0010"
down_revision: str | None = "20260514_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("min_quantity", sa.Numeric(12, 3), server_default="1", nullable=False))
    op.add_column("products", sa.Column("meta_title", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("meta_description", sa.String(length=500), nullable=True))
    op.create_table(
        "product_images",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('Europe/Moscow', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('Europe/Moscow', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_images_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_images")),
    )
    op.create_index(op.f("ix_product_images_product_id"), "product_images", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_product_images_product_id"), table_name="product_images")
    op.drop_table("product_images")
    op.drop_column("products", "meta_description")
    op.drop_column("products", "meta_title")
    op.drop_column("products", "min_quantity")
    op.drop_column("products", "description")
