"""Add optional prices per store."""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0074"
down_revision = "20261003_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("carts", sa.Column("store_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_carts_store_id", "carts", ["store_id"])
    op.create_foreign_key("fk_carts_store_id", "carts", "pickup_points", ["store_id"], ["id"], ondelete="SET NULL")
    op.add_column("product_stocks", sa.Column("price", sa.Numeric(12, 2), nullable=True))
    op.add_column("product_stocks", sa.Column("old_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("product_stocks", sa.Column("price_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_store_price_nonnegative", "product_stocks", "price IS NULL OR price >= 0")
    op.create_check_constraint("ck_store_old_price_valid", "product_stocks", "old_price IS NULL OR (price IS NOT NULL AND old_price >= price)")


def downgrade() -> None:
    op.drop_constraint("fk_carts_store_id", "carts", type_="foreignkey")
    op.drop_index("ix_carts_store_id", table_name="carts")
    op.drop_column("carts", "store_id")
    op.drop_constraint("ck_store_old_price_valid", "product_stocks", type_="check")
    op.drop_constraint("ck_store_price_nonnegative", "product_stocks", type_="check")
    op.drop_column("product_stocks", "price_updated_at")
    op.drop_column("product_stocks", "old_price")
    op.drop_column("product_stocks", "price")
