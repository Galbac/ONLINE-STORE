"""add user unblock fields

Revision ID: 20260520_0033
Revises: 20260520_0032
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0033"
down_revision: str | None = "20260520_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("unblocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("unblocked_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("unblock_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_users_unblocked_by_users"),
        "users",
        "users",
        ["unblocked_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_unblocked_by"), "users", ["unblocked_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_unblocked_by"), table_name="users")
    op.drop_constraint(op.f("fk_users_unblocked_by_users"), "users", type_="foreignkey")
    op.drop_column("users", "unblock_reason")
    op.drop_column("users", "unblocked_by")
    op.drop_column("users", "unblocked_at")
