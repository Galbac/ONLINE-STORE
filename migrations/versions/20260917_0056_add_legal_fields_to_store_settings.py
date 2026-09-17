"""add legal fields to store settings

Revision ID: 20260917_0056
Revises: 20260521_0055_create_integration_jobs
Create Date: 2026-09-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260917_0056'
down_revision: Union[str, None] = '20260521_0055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('store_settings', sa.Column('legal_name', sa.String(length=255), server_default='ИП Победа', nullable=True))
    op.add_column('store_settings', sa.Column('inn', sa.String(length=12), server_default='000000000000', nullable=True))
    op.add_column('store_settings', sa.Column('ogrn', sa.String(length=15), server_default='000000000000000', nullable=True))


def downgrade() -> None:
    op.drop_column('store_settings', 'ogrn')
    op.drop_column('store_settings', 'inn')
    op.drop_column('store_settings', 'legal_name')
