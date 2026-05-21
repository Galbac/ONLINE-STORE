"""add promo code soft delete fields

Revision ID: 20260521_0040
Revises: 20260521_0039
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0040"
down_revision: str | None = "20260521_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("promo_codes", sa.Column("deleted_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_promo_codes_deleted_by_users"),
        "promo_codes",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_promo_codes_deleted_by"), "promo_codes", ["deleted_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_codes_deleted_by"), table_name="promo_codes")
    op.drop_constraint(op.f("fk_promo_codes_deleted_by_users"), "promo_codes", type_="foreignkey")
    op.drop_column("promo_codes", "deleted_by")
    op.drop_column("promo_codes", "deleted_at")
