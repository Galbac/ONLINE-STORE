"""add order consent audit fields

Revision ID: 20260925_0068
Revises: 20260924_0067
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260925_0068'
down_revision: Union[str, None] = '20260924_0067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('user_ip', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('user_agent', sa.String(length=500), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('accepted_terms_version', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'accepted_at')
    op.drop_column('orders', 'accepted_terms_version')
    op.drop_column('orders', 'user_agent')
    op.drop_column('orders', 'user_ip')
