"""add order cancelled by user id

Revision ID: 20260520_0030
Revises: 20260520_0029
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0030"
down_revision: str | None = "20260520_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("cancelled_by_user_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_orders_cancelled_by_user_id"), "orders", ["cancelled_by_user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_orders_cancelled_by_user_id_users"),
        "orders",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_orders_cancelled_by_user_id_users"), "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_cancelled_by_user_id"), table_name="orders")
    op.drop_column("orders", "cancelled_by_user_id")
