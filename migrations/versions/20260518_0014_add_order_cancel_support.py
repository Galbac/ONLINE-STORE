"""add order cancel support

Revision ID: 20260518_0014
Revises: 20260518_0013
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0014"
down_revision: str | None = "20260518_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("cancelled_by", sa.String(length=50), nullable=True))
    op.add_column("promo_code_usages", sa.Column("order_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_promo_code_usages_order_id"), "promo_code_usages", ["order_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_promo_code_usages_order_id_orders"),
        "promo_code_usages",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_promo_code_usages_order_id_orders"), "promo_code_usages", type_="foreignkey")
    op.drop_index(op.f("ix_promo_code_usages_order_id"), table_name="promo_code_usages")
    op.drop_column("promo_code_usages", "order_id")
    op.drop_column("orders", "cancelled_by")
    op.drop_column("orders", "cancelled_at")
    op.drop_column("orders", "cancel_reason")
