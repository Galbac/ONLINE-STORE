"""add uploads

Revision ID: 20260518_0024
Revises: 20260518_0023
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260518_0024"
down_revision: str | None = "20260518_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("storage_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=True),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"], name=op.f("fk_uploads_deleted_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name=op.f("fk_uploads_uploaded_by_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
    )
    op.create_index(op.f("ix_uploads_uploaded_by"), "uploads", ["uploaded_by"], unique=False)
    op.create_index(op.f("ix_uploads_deleted_by"), "uploads", ["deleted_by"], unique=False)
    op.add_column("product_images", sa.Column("file_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_product_images_file_id"), "product_images", ["file_id"], unique=False)
    op.create_foreign_key(op.f("fk_product_images_file_id_uploads"), "product_images", "uploads", ["file_id"], ["id"], ondelete="SET NULL")
    op.add_column("categories", sa.Column("image_file_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_categories_image_file_id"), "categories", ["image_file_id"], unique=False)
    op.create_foreign_key(op.f("fk_categories_image_file_id_uploads"), "categories", "uploads", ["image_file_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(op.f("fk_categories_image_file_id_uploads"), "categories", type_="foreignkey")
    op.drop_index(op.f("ix_categories_image_file_id"), table_name="categories")
    op.drop_column("categories", "image_file_id")
    op.drop_constraint(op.f("fk_product_images_file_id_uploads"), "product_images", type_="foreignkey")
    op.drop_index(op.f("ix_product_images_file_id"), table_name="product_images")
    op.drop_column("product_images", "file_id")
    op.drop_index(op.f("ix_uploads_deleted_by"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_uploaded_by"), table_name="uploads")
    op.drop_table("uploads")
