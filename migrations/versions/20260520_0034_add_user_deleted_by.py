"""add user deleted_by

Revision ID: 20260520_0034
Revises: 20260520_0033
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0034"
down_revision: str | None = "20260520_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_deleted_by_users"),
        "users",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_deleted_by"), "users", ["deleted_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_deleted_by"), table_name="users")
    op.drop_constraint(op.f("fk_users_deleted_by_users"), "users", type_="foreignkey")
    op.drop_column("users", "deleted_by")
