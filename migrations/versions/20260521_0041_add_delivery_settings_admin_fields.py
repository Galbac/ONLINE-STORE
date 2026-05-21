"""add delivery settings admin fields

Revision ID: 20260521_0041
Revises: 20260521_0040
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0041"
down_revision: str | None = "20260521_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("delivery_settings", sa.Column("default_city", sa.String(length=100), server_default="Москва", nullable=False))
    op.add_column("delivery_settings", sa.Column("currency", sa.String(length=3), server_default="RUB", nullable=False))


def downgrade() -> None:
    op.drop_column("delivery_settings", "currency")
    op.drop_column("delivery_settings", "default_city")
