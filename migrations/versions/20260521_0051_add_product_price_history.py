"""add product price history

Revision ID: 20260521_0051
Revises: 20260521_0050
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0051"
down_revision: str | None = "20260521_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("currency", sa.String(length=3), server_default="RUB", nullable=False))
    op.add_column("products", sa.Column("price_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "product_price_history",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("old_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("new_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="1c", nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_price_history_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_price_history")),
    )
    op.create_index(op.f("ix_product_price_history_product_id"), "product_price_history", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_product_price_history_product_id"), table_name="product_price_history")
    op.drop_table("product_price_history")
    op.drop_column("products", "price_updated_at")
    op.drop_column("products", "currency")
