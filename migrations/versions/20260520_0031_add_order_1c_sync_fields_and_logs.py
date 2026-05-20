"""add order 1c sync fields and logs

Revision ID: 20260520_0031
Revises: 20260520_0030
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0031"
down_revision: str | None = "20260520_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("sync_error", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_orders_external_1c_id"), "orders", ["external_1c_id"], unique=False)
    op.create_table(
        "integration_logs",
        sa.Column("system", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_logs")),
    )
    op.create_index(op.f("ix_integration_logs_action"), "integration_logs", ["action"], unique=False)
    op.create_index(op.f("ix_integration_logs_entity_id"), "integration_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_integration_logs_entity_type"), "integration_logs", ["entity_type"], unique=False)
    op.create_index(op.f("ix_integration_logs_status"), "integration_logs", ["status"], unique=False)
    op.create_index(op.f("ix_integration_logs_system"), "integration_logs", ["system"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_logs_system"), table_name="integration_logs")
    op.drop_index(op.f("ix_integration_logs_status"), table_name="integration_logs")
    op.drop_index(op.f("ix_integration_logs_entity_type"), table_name="integration_logs")
    op.drop_index(op.f("ix_integration_logs_entity_id"), table_name="integration_logs")
    op.drop_index(op.f("ix_integration_logs_action"), table_name="integration_logs")
    op.drop_table("integration_logs")
    op.drop_index(op.f("ix_orders_external_1c_id"), table_name="orders")
    op.drop_column("orders", "last_sync_at")
    op.drop_column("orders", "sync_error")
    op.drop_column("orders", "external_1c_id")
