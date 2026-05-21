"""add promo code soft delete flag

Revision ID: 20260521_0039
Revises: 20260521_0038
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0039"
down_revision: str | None = "20260521_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("promo_codes", "is_deleted")
