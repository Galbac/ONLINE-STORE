"""add promo codes

Revision ID: 20260515_0012
Revises: 20260514_0011
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260515_0012"
down_revision: str | None = "20260514_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("per_user_usage_limit", sa.Integer(), nullable=True),
        sa.Column("applicable_category_id", sa.BigInteger(), nullable=True),
        sa.Column("applicable_product_id", sa.BigInteger(), nullable=True),
        sa.Column("allow_discounted_products", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["applicable_category_id"], ["categories.id"], name=op.f("fk_promo_codes_applicable_category_id_categories"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applicable_product_id"], ["products.id"], name=op.f("fk_promo_codes_applicable_product_id_products"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promo_codes")),
    )
    op.create_index(op.f("ix_promo_codes_code"), "promo_codes", ["code"], unique=True)
    op.create_index(op.f("ix_promo_codes_applicable_category_id"), "promo_codes", ["applicable_category_id"], unique=False)
    op.create_index(op.f("ix_promo_codes_applicable_product_id"), "promo_codes", ["applicable_product_id"], unique=False)
    op.create_table(
        "promo_code_usages",
        sa.Column("promo_code_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], name=op.f("fk_promo_code_usages_promo_code_id_promo_codes"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_promo_code_usages_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promo_code_usages")),
    )
    op.create_index(op.f("ix_promo_code_usages_promo_code_id"), "promo_code_usages", ["promo_code_id"], unique=False)
    op.create_index(op.f("ix_promo_code_usages_user_id"), "promo_code_usages", ["user_id"], unique=False)
    op.add_column("carts", sa.Column("promo_code_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_carts_promo_code_id"), "carts", ["promo_code_id"], unique=False)
    op.create_foreign_key(op.f("fk_carts_promo_code_id_promo_codes"), "carts", "promo_codes", ["promo_code_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(op.f("fk_carts_promo_code_id_promo_codes"), "carts", type_="foreignkey")
    op.drop_index(op.f("ix_carts_promo_code_id"), table_name="carts")
    op.drop_column("carts", "promo_code_id")
    op.drop_index(op.f("ix_promo_code_usages_user_id"), table_name="promo_code_usages")
    op.drop_index(op.f("ix_promo_code_usages_promo_code_id"), table_name="promo_code_usages")
    op.drop_table("promo_code_usages")
    op.drop_index(op.f("ix_promo_codes_applicable_product_id"), table_name="promo_codes")
    op.drop_index(op.f("ix_promo_codes_applicable_category_id"), table_name="promo_codes")
    op.drop_index(op.f("ix_promo_codes_code"), table_name="promo_codes")
    op.drop_table("promo_codes")
