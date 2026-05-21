"""add pickup point soft delete fields

Revision ID: 20260521_0045
Revises: 20260521_0044
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0045"
down_revision: str | None = "20260521_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pickup_points", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("pickup_points", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_pickup_points_is_deleted"), "pickup_points", ["is_deleted"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pickup_points_is_deleted"), table_name="pickup_points")
    op.drop_column("pickup_points", "deleted_at")
    op.drop_column("pickup_points", "is_deleted")
