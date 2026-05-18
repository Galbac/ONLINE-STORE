"""add order creation support

Revision ID: 20260518_0013
Revises: 20260515_0012
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0013"
down_revision: str | None = "20260515_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pickup_points",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pickup_points")),
    )
    op.add_column("orders", sa.Column("pickup_point_id", sa.BigInteger(), nullable=True))
    op.add_column("orders", sa.Column("delivery_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("delivery_time_slot_id", sa.BigInteger(), nullable=True))
    op.add_column("orders", sa.Column("delivery_price", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("subtotal", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("promo_discount_amount", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("customer_name", sa.String(length=100), server_default="", nullable=False))
    op.add_column("orders", sa.Column("customer_phone", sa.String(length=32), server_default="", nullable=False))
    op.add_column("orders", sa.Column("customer_email", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("sync_status", sa.String(length=50), server_default="pending", nullable=False))
    op.create_index(op.f("ix_orders_pickup_point_id"), "orders", ["pickup_point_id"], unique=False)
    op.create_foreign_key(op.f("fk_orders_pickup_point_id_pickup_points"), "orders", "pickup_points", ["pickup_point_id"], ["id"], ondelete="SET NULL")
    op.add_column("order_items", sa.Column("product_slug", sa.String(length=255), server_default="", nullable=False))
    op.add_column("order_items", sa.Column("product_type", sa.String(length=20), server_default="piece", nullable=False))
    op.add_column("order_items", sa.Column("old_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("order_items", sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("order_items", sa.Column("total_price", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("order_items", sa.Column("final_price", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("promo_code_usages", sa.Column("status", sa.String(length=20), server_default="reserved", nullable=False))
    op.create_table(
        "payments",
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("payment_url", sa.String(length=500), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_payments_order_id_orders"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"], unique=False)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_column("promo_code_usages", "status")
    op.drop_column("order_items", "final_price")
    op.drop_column("order_items", "total_price")
    op.drop_column("order_items", "discount_amount")
    op.drop_column("order_items", "old_price")
    op.drop_column("order_items", "product_type")
    op.drop_column("order_items", "product_slug")
    op.drop_constraint(op.f("fk_orders_pickup_point_id_pickup_points"), "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_pickup_point_id"), table_name="orders")
    op.drop_column("orders", "sync_status")
    op.drop_column("orders", "comment")
    op.drop_column("orders", "customer_email")
    op.drop_column("orders", "customer_phone")
    op.drop_column("orders", "customer_name")
    op.drop_column("orders", "promo_discount_amount")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "subtotal")
    op.drop_column("orders", "delivery_price")
    op.drop_column("orders", "delivery_time_slot_id")
    op.drop_column("orders", "delivery_date")
    op.drop_column("orders", "pickup_point_id")
    op.drop_table("pickup_points")
