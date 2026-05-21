"""add pickup point deleted by

Revision ID: 20260521_0046
Revises: 20260521_0045
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0046"
down_revision: str | None = "20260521_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pickup_points", sa.Column("deleted_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_pickup_points_deleted_by_users"),
        "pickup_points",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_pickup_points_deleted_by"), "pickup_points", ["deleted_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pickup_points_deleted_by"), table_name="pickup_points")
    op.drop_constraint(op.f("fk_pickup_points_deleted_by_users"), "pickup_points", type_="foreignkey")
    op.drop_column("pickup_points", "deleted_by")
