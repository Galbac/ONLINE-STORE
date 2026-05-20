"""add user block fields

Revision ID: 20260520_0032
Revises: 20260520_0031
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0032"
down_revision: str | None = "20260520_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_blocked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("blocked_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("block_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_users_blocked_by_users"),
        "users",
        "users",
        ["blocked_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_blocked_by"), "users", ["blocked_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_blocked_by"), table_name="users")
    op.drop_constraint(op.f("fk_users_blocked_by_users"), "users", type_="foreignkey")
    op.drop_column("users", "block_reason")
    op.drop_column("users", "blocked_by")
    op.drop_column("users", "blocked_at")
    op.drop_column("users", "is_blocked")
