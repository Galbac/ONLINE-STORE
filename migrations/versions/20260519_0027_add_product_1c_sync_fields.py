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
    op.add_column("product_images", sa.Column("is_main", sa.Boolean(), server_default="false", nullable=False))
    op.create_index(op.f("ix_products_external_1c_id"), "products", ["external_1c_id"], unique=False)
    op.create_index(op.f("ix_products_sync_status"), "products", ["sync_status"], unique=False)
    op.create_table(
        "product_availability_logs",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="success", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_availability_logs_product_id_products"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_availability_logs")),
    )
    op.create_index(op.f("ix_product_availability_logs_product_id"), "product_availability_logs", ["product_id"], unique=False)
    op.create_index(op.f("ix_product_availability_logs_user_id"), "product_availability_logs", ["user_id"], unique=False)
    op.create_table(
        "stock_movements",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("previous_stock_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("new_stock_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("low_stock_threshold", sa.Numeric(12, 3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_movements_product_id_products"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    op.create_index(op.f("ix_stock_movements_product_id"), "stock_movements", ["product_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_user_id"), "stock_movements", ["user_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_operation"), "stock_movements", ["operation"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_movements_operation"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_user_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_product_id"), table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index(op.f("ix_product_availability_logs_user_id"), table_name="product_availability_logs")
    op.drop_index(op.f("ix_product_availability_logs_product_id"), table_name="product_availability_logs")
    op.drop_table("product_availability_logs")
    op.drop_index(op.f("ix_products_sync_status"), table_name="products")
    op.drop_index(op.f("ix_products_external_1c_id"), table_name="products")
    op.drop_column("products", "deleted_by")
    op.drop_column("product_images", "is_main")
    op.drop_column("products", "low_stock_threshold")
    op.drop_column("products", "sync_status")
    op.drop_column("products", "external_1c_id")
