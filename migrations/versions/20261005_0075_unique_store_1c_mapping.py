"""Ensure each 1C warehouse identifies exactly one store."""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0075"
down_revision = "20261005_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("uq_active_pickup_point_1c", "pickup_points", ["external_1c_id"], unique=True,
                    postgresql_where=sa.text("external_1c_id IS NOT NULL AND is_deleted = false"))


def downgrade() -> None:
    op.drop_index("uq_active_pickup_point_1c", table_name="pickup_points")
