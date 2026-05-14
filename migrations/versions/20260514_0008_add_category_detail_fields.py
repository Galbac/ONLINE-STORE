"""add category detail fields

Revision ID: 20260514_0008
Revises: 20260514_0007
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0008"
down_revision: str | None = "20260514_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("categories", sa.Column("meta_title", sa.String(length=255), nullable=True))
    op.add_column("categories", sa.Column("meta_description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("categories", "meta_description")
    op.drop_column("categories", "meta_title")
    op.drop_column("categories", "description")
