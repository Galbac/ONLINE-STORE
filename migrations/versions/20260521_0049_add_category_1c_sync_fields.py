"""add category 1c sync fields

Revision ID: 20260521_0049
Revises: 20260521_0048
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0049"
down_revision: str | None = "20260521_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("categories", sa.Column("sync_status", sa.String(length=50), nullable=True))
    op.add_column("categories", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_categories_external_1c_id"), "categories", ["external_1c_id"], unique=True)
    op.create_index(op.f("ix_categories_sync_status"), "categories", ["sync_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_categories_sync_status"), table_name="categories")
    op.drop_index(op.f("ix_categories_external_1c_id"), table_name="categories")
    op.drop_column("categories", "last_sync_at")
    op.drop_column("categories", "sync_status")
    op.drop_column("categories", "external_1c_id")
