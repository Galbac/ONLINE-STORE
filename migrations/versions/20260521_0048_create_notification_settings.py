"""create notification settings

Revision ID: 20260521_0048
Revises: 20260521_0047
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0048"
down_revision: str | None = "20260521_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("email_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("email_from", sa.String(length=255), nullable=True),
        sa.Column("email_sender_name", sa.String(length=255), server_default="Супермаркет", nullable=False),
        sa.Column("telegram_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("telegram_admin_chat_id", sa.String(length=100), nullable=True),
        sa.Column("notify_admin_new_order", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_admin_payment_error", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_admin_1c_error", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_customer_order_created", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_customer_order_status", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_customer_payment", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_customer_delivery", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_settings")),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
