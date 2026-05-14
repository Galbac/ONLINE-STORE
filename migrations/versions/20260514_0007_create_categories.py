"""create categories

Revision ID: 20260514_0007
Revises: 20260513_0006
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0007"
down_revision: str | None = "20260513_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('Europe/Moscow', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('Europe/Moscow', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(op.f("ix_categories_parent_id"), "categories", ["parent_id"], unique=False)
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"], unique=True)
    op.add_column("products", sa.Column("category_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_products_category_id_categories"),
        "products",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_products_category_id_categories"), "products", type_="foreignkey")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_column("products", "category_id")
    op.drop_index(op.f("ix_categories_slug"), table_name="categories")
    op.drop_index(op.f("ix_categories_parent_id"), table_name="categories")
    op.drop_table("categories")
