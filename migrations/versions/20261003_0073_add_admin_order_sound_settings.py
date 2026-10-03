"""add admin order sound settings

Revision ID: 20261003_0073
Revises: 20261003_0072
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261003_0073"
down_revision: str | None = "20261003_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column("admin_order_sound_enabled", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "notification_settings",
        sa.Column("admin_order_sound_volume", sa.Float(), server_default="0.5", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "admin_order_sound_volume")
    op.drop_column("notification_settings", "admin_order_sound_enabled")
