"""add loyalty and telegram connect

Revision ID: 20260918_0058
Revises: 20260918_0057
Create Date: 2026-09-18 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260918_0058'
down_revision: Union[str, None] = '20260918_0057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_chat_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_users_telegram_chat_id'), 'users', ['telegram_chat_id'], unique=True)

    op.create_table(
        'loyalty_accounts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('balance', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_loyalty_accounts_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_loyalty_accounts')),
    )
    op.create_index(op.f('ix_loyalty_accounts_user_id'), 'loyalty_accounts', ['user_id'], unique=True)

    op.create_table(
        'loyalty_transactions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_loyalty_transactions_order_id_orders'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_loyalty_transactions_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_loyalty_transactions')),
    )
    op.create_index(op.f('ix_loyalty_transactions_order_id'), 'loyalty_transactions', ['order_id'], unique=False)
    op.create_index(op.f('ix_loyalty_transactions_user_id'), 'loyalty_transactions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_loyalty_transactions_user_id'), table_name='loyalty_transactions')
    op.drop_index(op.f('ix_loyalty_transactions_order_id'), table_name='loyalty_transactions')
    op.drop_table('loyalty_transactions')
    op.drop_index(op.f('ix_loyalty_accounts_user_id'), table_name='loyalty_accounts')
    op.drop_table('loyalty_accounts')
    op.drop_index(op.f('ix_users_telegram_chat_id'), table_name='users')
    op.drop_column('users', 'telegram_chat_id')
