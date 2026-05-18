"""add delivery settings

Revision ID: 20260518_0020
Revises: 20260518_0019
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0020"
down_revision: str | None = "20260518_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_settings",
        sa.Column("delivery_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("delivery_title", sa.String(length=255), server_default="Доставка", nullable=False),
        sa.Column("delivery_description", sa.Text(), server_default="Доставка по городу", nullable=False),
        sa.Column("min_order_amount", sa.Numeric(12, 2), server_default="1000.00", nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2), server_default="250.00", nullable=False),
        sa.Column("free_from_amount", sa.Numeric(12, 2), server_default="3000.00", nullable=True),
        sa.Column("has_time_slots", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("pickup_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("pickup_title", sa.String(length=255), server_default="Самовывоз", nullable=False),
        sa.Column("pickup_description", sa.Text(), server_default="Можно забрать заказ из магазина", nullable=False),
        sa.Column("pickup_price", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_settings")),
    )
    op.execute(
        """
        INSERT INTO delivery_settings (
            delivery_enabled,
            delivery_title,
            delivery_description,
            min_order_amount,
            base_price,
            free_from_amount,
            has_time_slots,
            pickup_enabled,
            pickup_title,
            pickup_description,
            pickup_price
        )
        VALUES (
            true,
            'Доставка',
            'Доставка по городу',
            1000.00,
            250.00,
            3000.00,
            true,
            true,
            'Самовывоз',
            'Можно забрать заказ из магазина',
            0
        )
        """
    )


def downgrade() -> None:
    op.drop_table("delivery_settings")
