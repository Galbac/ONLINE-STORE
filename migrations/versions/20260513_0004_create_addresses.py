"""create addresses

Revision ID: 20260513_0004
Revises: 20260513_0003
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260513_0004"
down_revision: str | None = "20260513_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "addresses",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("street", sa.String(length=150), nullable=False),
        sa.Column("house", sa.String(length=50), nullable=False),
        sa.Column("building", sa.String(length=50), nullable=True),
        sa.Column("apartment", sa.String(length=50), nullable=True),
        sa.Column("entrance", sa.String(length=50), nullable=True),
        sa.Column("floor", sa.String(length=50), nullable=True),
        sa.Column("intercom", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_addresses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(op.f("ix_addresses_user_id"), "addresses", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_addresses_user_id"), table_name="addresses")
    op.drop_table("addresses")
