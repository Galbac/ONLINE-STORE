"""add discounts and favorites

Revision ID: 20260518_0023
Revises: 20260518_0022
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0023"
down_revision: str | None = "20260518_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discounts",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("applicable_product_id", sa.BigInteger(), nullable=True),
        sa.Column("applicable_category_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["applicable_category_id"], ["categories.id"], name=op.f("fk_discounts_applicable_category_id_categories"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applicable_product_id"], ["products.id"], name=op.f("fk_discounts_applicable_product_id_products"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discounts")),
    )
    op.create_index(op.f("ix_discounts_type"), "discounts", ["type"], unique=False)
    op.create_index(op.f("ix_discounts_applicable_category_id"), "discounts", ["applicable_category_id"], unique=False)
    op.create_index(op.f("ix_discounts_applicable_product_id"), "discounts", ["applicable_product_id"], unique=False)

    op.create_table(
        "favorites",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_favorites_product_id_products"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_favorites_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_favorites")),
        sa.UniqueConstraint("user_id", "product_id", name="uq_favorites_user_id_product_id"),
    )
    op.create_index(op.f("ix_favorites_product_id"), "favorites", ["product_id"], unique=False)
    op.create_index(op.f("ix_favorites_user_id"), "favorites", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_favorites_user_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_product_id"), table_name="favorites")
    op.drop_table("favorites")
    op.drop_index(op.f("ix_discounts_applicable_product_id"), table_name="discounts")
    op.drop_index(op.f("ix_discounts_applicable_category_id"), table_name="discounts")
    op.drop_index(op.f("ix_discounts_type"), table_name="discounts")
    op.drop_table("discounts")
