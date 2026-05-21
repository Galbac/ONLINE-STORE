"""add delivery zone soft delete relations

Revision ID: 20260521_0044
Revises: 20260521_0043
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0044"
down_revision: str | None = "20260521_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("delivery_zones", sa.Column("deleted_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_delivery_zones_deleted_by_users"),
        "delivery_zones",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_delivery_zones_deleted_by"), "delivery_zones", ["deleted_by"], unique=False)

    op.add_column("orders", sa.Column("delivery_zone_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_orders_delivery_zone_id_delivery_zones"),
        "orders",
        "delivery_zones",
        ["delivery_zone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_orders_delivery_zone_id"), "orders", ["delivery_zone_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_delivery_zone_id"), table_name="orders")
    op.drop_constraint(op.f("fk_orders_delivery_zone_id_delivery_zones"), "orders", type_="foreignkey")
    op.drop_column("orders", "delivery_zone_id")

    op.drop_index(op.f("ix_delivery_zones_deleted_by"), table_name="delivery_zones")
    op.drop_constraint(op.f("fk_delivery_zones_deleted_by_users"), "delivery_zones", type_="foreignkey")
    op.drop_column("delivery_zones", "deleted_by")
