"""add privacy and marketing consent to users

Revision ID: 20260921_0062
Revises: 20260921_0061
Create Date: 2026-09-21 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260921_0062'
down_revision: Union[str, None] = '20260921_0061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('agreed_to_privacy', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('agreed_to_privacy_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('marketing_consent', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('marketing_consent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'marketing_consent_at')
    op.drop_column('users', 'marketing_consent')
    op.drop_column('users', 'agreed_to_privacy_at')
    op.drop_column('users', 'agreed_to_privacy')
