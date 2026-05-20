"""add order internal comment

Revision ID: 20260520_0029
Revises: 20260520_0028
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0029"
down_revision: str | None = "20260520_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("internal_comment", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "internal_comment")
