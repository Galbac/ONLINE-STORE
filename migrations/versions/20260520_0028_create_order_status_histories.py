"""create order status histories

Revision ID: 20260520_0028
Revises: 20260519_0027
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0028"
down_revision: str | None = "20260519_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_status_histories",
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("old_status", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('Europe/Moscow', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('Europe/Moscow', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_status_histories_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_status_histories")),
    )
    op.create_index(op.f("ix_order_status_histories_changed_by"), "order_status_histories", ["changed_by"], unique=False)
    op.create_index(op.f("ix_order_status_histories_order_id"), "order_status_histories", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_status_histories_status"), "order_status_histories", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_order_status_histories_status"), table_name="order_status_histories")
    op.drop_index(op.f("ix_order_status_histories_order_id"), table_name="order_status_histories")
    op.drop_index(op.f("ix_order_status_histories_changed_by"), table_name="order_status_histories")
    op.drop_table("order_status_histories")
