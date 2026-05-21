"""add promo code create fields and relations

Revision ID: 20260521_0038
Revises: 20260521_0037
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0038"
down_revision: str | None = "20260521_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("description", sa.String(length=1000), nullable=True))
    op.add_column("promo_codes", sa.Column("max_discount_amount", sa.Numeric(12, 2), nullable=True))

    op.create_table(
        "promo_code_products",
        sa.Column("promo_code_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_promo_code_products_product_id_products"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], name=op.f("fk_promo_code_products_promo_code_id_promo_codes"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promo_code_products")),
        sa.UniqueConstraint("promo_code_id", "product_id", name="uq_promo_code_products_promo_code_id_product_id"),
    )
    op.create_index(op.f("ix_promo_code_products_product_id"), "promo_code_products", ["product_id"], unique=False)
    op.create_index(op.f("ix_promo_code_products_promo_code_id"), "promo_code_products", ["promo_code_id"], unique=False)

    op.create_table(
        "promo_code_categories",
        sa.Column("promo_code_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name=op.f("fk_promo_code_categories_category_id_categories"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], name=op.f("fk_promo_code_categories_promo_code_id_promo_codes"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promo_code_categories")),
        sa.UniqueConstraint("promo_code_id", "category_id", name="uq_promo_code_categories_promo_code_id_category_id"),
    )
    op.create_index(op.f("ix_promo_code_categories_category_id"), "promo_code_categories", ["category_id"], unique=False)
    op.create_index(op.f("ix_promo_code_categories_promo_code_id"), "promo_code_categories", ["promo_code_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_code_categories_promo_code_id"), table_name="promo_code_categories")
    op.drop_index(op.f("ix_promo_code_categories_category_id"), table_name="promo_code_categories")
    op.drop_table("promo_code_categories")
    op.drop_index(op.f("ix_promo_code_products_promo_code_id"), table_name="promo_code_products")
    op.drop_index(op.f("ix_promo_code_products_product_id"), table_name="promo_code_products")
    op.drop_table("promo_code_products")
    op.drop_column("promo_codes", "max_discount_amount")
    op.drop_column("promo_codes", "description")
