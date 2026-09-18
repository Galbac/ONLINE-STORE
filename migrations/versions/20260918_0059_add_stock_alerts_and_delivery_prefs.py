"""add stock alerts and delivery prefs

Revision ID: 20260918_0059
Revises: 20260918_0058
Create Date: 2026-09-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260918_0059'
down_revision: Union[str, None] = '20260918_0058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('leave_at_door', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('orders', sa.Column('dont_ring_doorbell', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('orders', sa.Column('substitution_policy', sa.String(length=50), server_default='call', nullable=False))

    op.create_table(
        'stock_alerts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('is_notified', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_stock_alerts_product_id_products'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_stock_alerts_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_alerts')),
    )
    op.create_index(op.f('ix_stock_alerts_product_id'), 'stock_alerts', ['product_id'], unique=False)
    op.create_index(op.f('ix_stock_alerts_user_id'), 'stock_alerts', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_stock_alerts_user_id'), table_name='stock_alerts')
    op.drop_index(op.f('ix_stock_alerts_product_id'), table_name='stock_alerts')
    op.drop_table('stock_alerts')
    op.drop_column('orders', 'substitution_policy')
    op.drop_column('orders', 'dont_ring_doorbell')
    op.drop_column('orders', 'leave_at_door')
