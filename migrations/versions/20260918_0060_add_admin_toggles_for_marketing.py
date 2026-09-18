"""add admin toggles for marketing

Revision ID: 20260918_0060
Revises: 20260918_0059
Create Date: 2026-09-18 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260918_0060'
down_revision: Union[str, None] = '20260918_0059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('store_settings', sa.Column('promo_codes_enabled', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('store_settings', sa.Column('referral_program_enabled', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('store_settings', sa.Column('loyalty_program_enabled', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('store_settings', 'loyalty_program_enabled')
    op.drop_column('store_settings', 'referral_program_enabled')
    op.drop_column('store_settings', 'promo_codes_enabled')
