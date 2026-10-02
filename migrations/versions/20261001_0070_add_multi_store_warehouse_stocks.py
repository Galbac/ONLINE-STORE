"""add multi store warehouse stocks

Revision ID: 20261001_0070
Revises: 20260925_0069
Create Date: 2026-10-01 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20261001_0070'
down_revision: Union[str, None] = '20260925_0069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Alter pickup_points
    op.add_column(
        'pickup_points',
        sa.Column('external_1c_id', sa.String(length=100), nullable=True),
    )
    op.create_index(op.f('ix_pickup_points_external_1c_id'), 'pickup_points', ['external_1c_id'], unique=False)
    op.add_column(
        'pickup_points',
        sa.Column('is_warehouse', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )

    # 2. Create product_stocks
    op.create_table(
        'product_stocks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('pickup_point_id', sa.BigInteger(), nullable=False),
        sa.Column('stock_quantity', sa.Numeric(precision=12, scale=3), server_default=sa.text('0'), nullable=False),
        sa.Column('reserved_quantity', sa.Numeric(precision=12, scale=3), server_default=sa.text('0'), nullable=False),
        sa.Column('low_stock_threshold', sa.Numeric(precision=12, scale=3), server_default=sa.text('5'), nullable=False),
        sa.Column('stock_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['pickup_point_id'], ['pickup_points.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'pickup_point_id', name='uq_product_pickup_point_stock'),
    )
    op.create_index(op.f('ix_product_stocks_pickup_point_id'), 'product_stocks', ['pickup_point_id'], unique=False)
    op.create_index(op.f('ix_product_stocks_product_id'), 'product_stocks', ['product_id'], unique=False)

    # 3. Alter delivery_zones
    op.add_column(
        'delivery_zones',
        sa.Column('warehouse_id', sa.BigInteger(), nullable=True),
    )
    op.create_index(op.f('ix_delivery_zones_warehouse_id'), 'delivery_zones', ['warehouse_id'], unique=False)
    op.create_foreign_key(
        'fk_delivery_zones_warehouse_id_pickup_points',
        'delivery_zones',
        'pickup_points',
        ['warehouse_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 4. Alter users
    op.add_column(
        'users',
        sa.Column('assigned_pickup_point_id', sa.BigInteger(), nullable=True),
    )
    op.create_index(op.f('ix_users_assigned_pickup_point_id'), 'users', ['assigned_pickup_point_id'], unique=False)
    op.create_foreign_key(
        'fk_users_assigned_pickup_point_id_pickup_points',
        'users',
        'pickup_points',
        ['assigned_pickup_point_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 5. Alter orders
    op.add_column(
        'orders',
        sa.Column('fulfilling_store_id', sa.BigInteger(), nullable=True),
    )
    op.create_index(op.f('ix_orders_fulfilling_store_id'), 'orders', ['fulfilling_store_id'], unique=False)
    op.create_foreign_key(
        'fk_orders_fulfilling_store_id_pickup_points',
        'orders',
        'pickup_points',
        ['fulfilling_store_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 6. Data backfill: populate product_stocks for existing products if at least one pickup point exists
    op.execute(
        """
        INSERT INTO product_stocks (product_id, pickup_point_id, stock_quantity, reserved_quantity, low_stock_threshold, stock_updated_at, created_date, updated_date)
        SELECT p.id, pp.id, p.stock_quantity, p.reserved_quantity, p.low_stock_threshold, p.stock_updated_at, now(), now()
        FROM products p
        CROSS JOIN LATERAL (
            SELECT id FROM pickup_points WHERE is_deleted = false ORDER BY id ASC LIMIT 1
        ) pp
        ON CONFLICT (product_id, pickup_point_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_constraint('fk_orders_fulfilling_store_id_pickup_points', 'orders', type_='foreignkey')
    op.drop_index(op.f('ix_orders_fulfilling_store_id'), table_name='orders')
    op.drop_column('orders', 'fulfilling_store_id')

    op.drop_constraint('fk_users_assigned_pickup_point_id_pickup_points', 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_assigned_pickup_point_id'), table_name='users')
    op.drop_column('users', 'assigned_pickup_point_id')

    op.drop_constraint('fk_delivery_zones_warehouse_id_pickup_points', 'delivery_zones', type_='foreignkey')
    op.drop_index(op.f('ix_delivery_zones_warehouse_id'), table_name='delivery_zones')
    op.drop_column('delivery_zones', 'warehouse_id')

    op.drop_index(op.f('ix_product_stocks_product_id'), table_name='product_stocks')
    op.drop_index(op.f('ix_product_stocks_pickup_point_id'), table_name='product_stocks')
    op.drop_table('product_stocks')

    op.drop_column('pickup_points', 'is_warehouse')
    op.drop_index(op.f('ix_pickup_points_external_1c_id'), table_name='pickup_points')
    op.drop_column('pickup_points', 'external_1c_id')
