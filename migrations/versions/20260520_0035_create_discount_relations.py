"""create discount relations

Revision ID: 20260520_0035
Revises: 20260520_0034
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0035"
down_revision: str | None = "20260520_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discount_products",
        sa.Column("discount_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["discount_id"], ["discounts.id"], name=op.f("fk_discount_products_discount_id_discounts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_discount_products_product_id_products"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_products")),
        sa.UniqueConstraint("discount_id", "product_id", name="uq_discount_products_discount_id_product_id"),
    )
    op.create_index(op.f("ix_discount_products_discount_id"), "discount_products", ["discount_id"], unique=False)
    op.create_index(op.f("ix_discount_products_product_id"), "discount_products", ["product_id"], unique=False)

    op.create_table(
        "discount_categories",
        sa.Column("discount_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name=op.f("fk_discount_categories_category_id_categories"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discount_id"], ["discounts.id"], name=op.f("fk_discount_categories_discount_id_discounts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_categories")),
        sa.UniqueConstraint("discount_id", "category_id", name="uq_discount_categories_discount_id_category_id"),
    )
    op.create_index(op.f("ix_discount_categories_category_id"), "discount_categories", ["category_id"], unique=False)
    op.create_index(op.f("ix_discount_categories_discount_id"), "discount_categories", ["discount_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_discount_categories_discount_id"), table_name="discount_categories")
    op.drop_index(op.f("ix_discount_categories_category_id"), table_name="discount_categories")
    op.drop_table("discount_categories")
    op.drop_index(op.f("ix_discount_products_product_id"), table_name="discount_products")
    op.drop_index(op.f("ix_discount_products_discount_id"), table_name="discount_products")
    op.drop_table("discount_products")
