"""Persist order request identity."""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0077"
down_revision = "20261005_0076"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("orders", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_orders_user_idempotency", "orders", ["user_id", "idempotency_key"]
    )


def downgrade():
    op.drop_constraint("uq_orders_user_idempotency", "orders", type_="unique")
    op.drop_column("orders", "request_hash")
    op.drop_column("orders", "idempotency_key")
