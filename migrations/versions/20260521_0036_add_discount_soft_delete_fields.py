"""add discount soft delete fields

Revision ID: 20260521_0036
Revises: 20260520_0035
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0036"
down_revision: str | None = "20260520_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("discounts", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("discounts", sa.Column("deleted_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_discounts_deleted_by_users"),
        "discounts",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_discounts_deleted_by"), "discounts", ["deleted_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_discounts_deleted_by"), table_name="discounts")
    op.drop_constraint(op.f("fk_discounts_deleted_by_users"), "discounts", type_="foreignkey")
    op.drop_column("discounts", "deleted_by")
    op.drop_column("discounts", "deleted_at")
