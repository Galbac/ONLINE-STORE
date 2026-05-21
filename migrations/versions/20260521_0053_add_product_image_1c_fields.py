"""add product image 1c fields

Revision ID: 20260521_0053
Revises: 20260521_0052
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0053"
down_revision: str | None = "20260521_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("product_images", sa.Column("image_external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("product_images", sa.Column("external_url", sa.String(length=500), nullable=True))
    op.alter_column("uploads", "uploaded_by", existing_type=sa.BigInteger(), nullable=True)
    op.create_index(op.f("ix_product_images_image_external_1c_id"), "product_images", ["image_external_1c_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_product_images_image_external_1c_id"), table_name="product_images")
    op.alter_column("uploads", "uploaded_by", existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("product_images", "external_url")
    op.drop_column("product_images", "image_external_1c_id")
