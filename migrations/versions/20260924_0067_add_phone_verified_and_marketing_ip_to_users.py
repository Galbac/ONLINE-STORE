"""add phone verified and marketing ip to users

Revision ID: 20260924_0067
Revises: 20260923_0066
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260924_0067'
down_revision: Union[str, None] = '20260923_0066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_phone_verified', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('marketing_consent_ip', sa.String(length=45), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'marketing_consent_ip')
    op.drop_column('users', 'phone_verified_at')
    op.drop_column('users', 'is_phone_verified')
