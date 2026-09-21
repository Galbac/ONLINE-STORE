"""add legal doc urls to store settings

Revision ID: 20260921_0061
Revises: 20260918_0060
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260921_0061'
down_revision: Union[str, None] = '20260918_0060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('store_settings', sa.Column('privacy_policy_url', sa.String(length=500), server_default='/privacy', nullable=True))
    op.add_column('store_settings', sa.Column('user_agreement_url', sa.String(length=500), server_default='/offer', nullable=True))
    op.add_column('store_settings', sa.Column('personal_data_consent_url', sa.String(length=500), server_default='/personal-data-consent', nullable=True))


def downgrade() -> None:
    op.drop_column('store_settings', 'personal_data_consent_url')
    op.drop_column('store_settings', 'user_agreement_url')
    op.drop_column('store_settings', 'privacy_policy_url')
