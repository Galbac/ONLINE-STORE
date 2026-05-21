"""add promo code name

Revision ID: 20260521_0037
Revises: 20260521_0036
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0037"
down_revision: str | None = "20260521_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("promo_codes", "name")
