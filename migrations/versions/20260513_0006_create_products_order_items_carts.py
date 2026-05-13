"""create products order items carts

Revision ID: 20260513_0006
Revises: 20260513_0005
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260513_0006"
down_revision: str | None = "20260513_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("stock_quantity", sa.Numeric(12, 3), server_default="0", nullable=False),
        sa.Column("quantity_step", sa.Numeric(12, 3), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_table(
        "carts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_carts_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carts")),
    )
    op.create_index(op.f("ix_carts_user_id"), "carts", ["user_id"], unique=True)
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_order_items_order_id_orders"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_order_items_product_id_products"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_product_id"), "order_items", ["product_id"], unique=False)
    op.create_table(
        "cart_items",
        sa.Column("cart_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], name=op.f("fk_cart_items_cart_id_carts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_cart_items_product_id_products"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cart_items")),
    )
    op.create_index(op.f("ix_cart_items_cart_id"), "cart_items", ["cart_id"], unique=False)
    op.create_index(op.f("ix_cart_items_product_id"), "cart_items", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cart_items_product_id"), table_name="cart_items")
    op.drop_index(op.f("ix_cart_items_cart_id"), table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_index(op.f("ix_order_items_product_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index(op.f("ix_carts_user_id"), table_name="carts")
    op.drop_table("carts")
    op.drop_table("products")
