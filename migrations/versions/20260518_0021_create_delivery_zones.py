"""create delivery zones

Revision ID: 20260518_0021
Revises: 20260518_0020
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0021"
down_revision: str | None = "20260518_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_zones",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_zones")),
    )
    op.create_index(op.f("ix_delivery_zones_city"), "delivery_zones", ["city"], unique=False)
    op.execute(
        """
        INSERT INTO delivery_zones (name, city, price, is_active)
        VALUES ('Центральная зона', 'Москва', NULL, true)
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_delivery_zones_city"), table_name="delivery_zones")
    op.drop_table("delivery_zones")
