"""create store settings

Revision ID: 20260521_0047
Revises: 20260521_0046
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0047"
down_revision: str | None = "20260521_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store_settings",
        sa.Column("shop_name", sa.String(length=255), server_default="Супермаркет", nullable=False),
        sa.Column("phone", sa.String(length=32), server_default="+79990000000", nullable=True),
        sa.Column("email", sa.String(length=255), server_default="info@example.com", nullable=True),
        sa.Column("address", sa.String(length=500), server_default="Москва, ул. Тверская, 10", nullable=True),
        sa.Column("working_hours", sa.String(length=255), server_default="Пн-Вс 09:00-22:00", nullable=True),
        sa.Column("online_payment_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("pay_on_delivery_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("maintenance_mode", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_store_settings")),
    )


def downgrade() -> None:
    op.drop_table("store_settings")
