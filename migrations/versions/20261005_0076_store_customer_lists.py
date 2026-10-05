"""Keep independent carts and favorites for each store."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0076"
down_revision = "20261005_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("favorites", sa.Column("store_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_favorites_store_id", "favorites", "pickup_points", ["store_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_favorites_store_id", "favorites", ["store_id"])
    # Preserve existing lists in their last selected store; never duplicate them across stores.
    op.execute("UPDATE carts SET store_id = (SELECT id FROM pickup_points WHERE is_active AND NOT is_deleted ORDER BY sort_order, id LIMIT 1) WHERE store_id IS NULL")
    op.execute("UPDATE favorites f SET store_id = COALESCE((SELECT store_id FROM carts c WHERE c.user_id = f.user_id), (SELECT id FROM pickup_points WHERE is_active AND NOT is_deleted ORDER BY sort_order, id LIMIT 1))")
    op.drop_index("ix_carts_user_id", table_name="carts")
    op.create_index("ix_carts_user_id", "carts", ["user_id"])
    op.create_unique_constraint("uq_carts_user_store", "carts", ["user_id", "store_id"])
    op.drop_constraint("uq_favorites_user_id_product_id", "favorites", type_="unique")
    op.create_unique_constraint("uq_favorites_user_product_store", "favorites", ["user_id", "product_id", "store_id"])


def downgrade() -> None:
    # A rollback cannot collapse independent lists without losing customer data.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM carts GROUP BY user_id HAVING count(*) > 1 LIMIT 1")).first() or connection.execute(sa.text("SELECT 1 FROM favorites GROUP BY user_id, product_id HAVING count(*) > 1 LIMIT 1")).first():
        raise RuntimeError("Resolve store-specific customer lists before downgrading")
    op.drop_constraint("uq_favorites_user_product_store", "favorites", type_="unique")
    op.create_unique_constraint("uq_favorites_user_id_product_id", "favorites", ["user_id", "product_id"])
    op.drop_index("ix_favorites_store_id", table_name="favorites")
    op.drop_constraint("fk_favorites_store_id", "favorites", type_="foreignkey")
    op.drop_column("favorites", "store_id")
    op.drop_constraint("uq_carts_user_store", "carts", type_="unique")
    op.drop_index("ix_carts_user_id", table_name="carts")
    op.create_index("ix_carts_user_id", "carts", ["user_id"], unique=True)
