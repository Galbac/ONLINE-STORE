"""extend delivery zones for admin

Revision ID: 20260521_0043
Revises: 20260521_0042
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0043"
down_revision: str | None = "20260521_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("delivery_zones", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("delivery_zones", sa.Column("free_delivery_from", sa.Numeric(12, 2), nullable=True))
    op.add_column("delivery_zones", sa.Column("min_order_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("delivery_zones", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("delivery_zones", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("delivery_zones", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_delivery_zones_is_deleted"), "delivery_zones", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_delivery_zones_sort_order"), "delivery_zones", ["sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_delivery_zones_sort_order"), table_name="delivery_zones")
    op.drop_index(op.f("ix_delivery_zones_is_deleted"), table_name="delivery_zones")
    op.drop_column("delivery_zones", "deleted_at")
    op.drop_column("delivery_zones", "sort_order")
    op.drop_column("delivery_zones", "is_deleted")
    op.drop_column("delivery_zones", "min_order_amount")
    op.drop_column("delivery_zones", "free_delivery_from")
    op.drop_column("delivery_zones", "description")
