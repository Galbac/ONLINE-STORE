"""add order sync error code

Revision ID: 20260521_0054
Revises: 20260521_0053
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0054"
down_revision: str | None = "20260521_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("sync_error_code", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "sync_error_code")
