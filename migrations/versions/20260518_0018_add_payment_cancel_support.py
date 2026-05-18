"""add payment cancel support

Revision ID: 20260518_0018
Revises: 20260518_0017
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0018"
down_revision: str | None = "20260518_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "cancelled_at")
