"""add banners reviews and feedback

Revision ID: 20260918_0057
Revises: 20260917_0056
Create Date: 2026-09-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260918_0057'
down_revision: Union[str, None] = '20260917_0056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'banners',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('subtitle', sa.String(length=255), nullable=True),
        sa.Column('badge', sa.String(length=100), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('bg_color', sa.String(length=50), server_default='#059669', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_banners')),
    )

    op.create_table(
        'product_reviews',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('pros', sa.Text(), nullable=True),
        sa.Column('cons', sa.Text(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('is_approved', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_reviews_product_id_products'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_product_reviews_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_product_reviews')),
    )
    op.create_index(op.f('ix_product_reviews_product_id'), 'product_reviews', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_reviews_user_id'), 'product_reviews', ['user_id'], unique=False)

    op.create_table(
        'feedbacks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='new', nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_feedbacks_order_id_orders'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_feedbacks')),
    )


def downgrade() -> None:
    op.drop_table('feedbacks')
    op.drop_index(op.f('ix_product_reviews_user_id'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_product_id'), table_name='product_reviews')
    op.drop_table('product_reviews')
    op.drop_table('banners')
