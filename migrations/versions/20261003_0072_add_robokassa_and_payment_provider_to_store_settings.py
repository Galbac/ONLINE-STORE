"""add_robokassa_and_payment_provider_to_store_settings

Revision ID: 20261003_0072
Revises: 20261002_0071
Create Date: 2026-10-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20261003_0072"
down_revision: Union[str, None] = "20261002_0071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "store_settings",
        sa.Column(
            "payment_provider",
            sa.String(length=32),
            server_default="yookassa",
            nullable=False,
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "robokassa_merchant_login",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "robokassa_password_1",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "robokassa_password_2",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "robokassa_is_test",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "yookassa_shop_id",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "yookassa_secret_key",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("store_settings", "yookassa_secret_key")
    op.drop_column("store_settings", "yookassa_shop_id")
    op.drop_column("store_settings", "robokassa_is_test")
    op.drop_column("store_settings", "robokassa_password_2")
    op.drop_column("store_settings", "robokassa_password_1")
    op.drop_column("store_settings", "robokassa_merchant_login")
    op.drop_column("store_settings", "payment_provider")
