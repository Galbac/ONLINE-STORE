"""add pickup points and time slots

Revision ID: 20260518_0022
Revises: 20260518_0021
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0022"
down_revision: str | None = "20260518_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pickup_points", sa.Column("city", sa.String(length=100), server_default="", nullable=False))
    op.add_column("pickup_points", sa.Column("address", sa.String(length=500), server_default="", nullable=False))
    op.add_column("pickup_points", sa.Column("working_hours", sa.String(length=255), nullable=True))
    op.add_column("pickup_points", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("pickup_points", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("pickup_points", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("pickup_points", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("pickup_points", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.create_index(op.f("ix_pickup_points_city"), "pickup_points", ["city"], unique=False)

    op.create_table(
        "delivery_time_slots",
        sa.Column("delivery_type", sa.String(length=20), nullable=False),
        sa.Column("pickup_point_id", sa.BigInteger(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("weekdays", sa.String(length=20), server_default="0,1,2,3,4,5,6", nullable=False),
        sa.Column("orders_limit", sa.Integer(), server_default="10", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["pickup_point_id"], ["pickup_points.id"], name=op.f("fk_delivery_time_slots_pickup_point_id_pickup_points"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_time_slots")),
    )
    op.create_index(op.f("ix_delivery_time_slots_delivery_type"), "delivery_time_slots", ["delivery_type"], unique=False)
    op.create_index(op.f("ix_delivery_time_slots_pickup_point_id"), "delivery_time_slots", ["pickup_point_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_delivery_time_slots_pickup_point_id"), table_name="delivery_time_slots")
    op.drop_index(op.f("ix_delivery_time_slots_delivery_type"), table_name="delivery_time_slots")
    op.drop_table("delivery_time_slots")
    op.drop_index(op.f("ix_pickup_points_city"), table_name="pickup_points")
    op.drop_column("pickup_points", "sort_order")
    op.drop_column("pickup_points", "longitude")
    op.drop_column("pickup_points", "latitude")
    op.drop_column("pickup_points", "description")
    op.drop_column("pickup_points", "phone")
    op.drop_column("pickup_points", "working_hours")
    op.drop_column("pickup_points", "address")
    op.drop_column("pickup_points", "city")
