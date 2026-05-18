"""add payment webhook support

Revision ID: 20260518_0017
Revises: 20260518_0016
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0017"
down_revision: str | None = "20260518_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("refund_status", sa.String(length=50), nullable=True))
    op.create_table(
        "payment_webhook_logs",
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("payment_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processing_status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_webhook_logs")),
    )
    op.create_index(op.f("ix_payment_webhook_logs_provider_event_id"), "payment_webhook_logs", ["provider_event_id"], unique=True)
    op.create_index(op.f("ix_payment_webhook_logs_provider_payment_id"), "payment_webhook_logs", ["provider_payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_webhook_logs_provider_payment_id"), table_name="payment_webhook_logs")
    op.drop_index(op.f("ix_payment_webhook_logs_provider_event_id"), table_name="payment_webhook_logs")
    op.drop_table("payment_webhook_logs")
    op.drop_column("payments", "refund_status")
