"""allow nullable delivery comments

Revision ID: 20260521_0042
Revises: 20260521_0041
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0042"
down_revision: str | None = "20260521_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("delivery_settings", "delivery_description", existing_type=sa.Text(), nullable=True)
    op.alter_column("delivery_settings", "pickup_description", existing_type=sa.Text(), nullable=True)
    op.alter_column("delivery_settings", "default_city", existing_type=sa.String(length=100), nullable=True)


def downgrade() -> None:
    op.alter_column("delivery_settings", "default_city", existing_type=sa.String(length=100), nullable=False)
    op.alter_column("delivery_settings", "pickup_description", existing_type=sa.Text(), nullable=False)
    op.alter_column("delivery_settings", "delivery_description", existing_type=sa.Text(), nullable=False)
