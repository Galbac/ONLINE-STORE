"""add payment provider fields

Revision ID: 20260518_0015
Revises: 20260518_0014
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0015"
down_revision: str | None = "20260518_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("currency", sa.String(length=3), server_default="RUB", nullable=False))
    op.add_column("payments", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("payments", sa.Column("provider_payment_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_payments_provider_payment_id"), "payments", ["provider_payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_provider_payment_id"), table_name="payments")
    op.drop_column("payments", "provider_payment_id")
    op.drop_column("payments", "provider")
    op.drop_column("payments", "currency")
