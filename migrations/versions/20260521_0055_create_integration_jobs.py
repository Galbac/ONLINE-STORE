"""create integration jobs

Revision ID: 20260521_0055
Revises: 20260521_0054
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260521_0055"
down_revision: str | None = "20260521_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_jobs",
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_by", sa.BigInteger(), nullable=False),
        sa.Column("full_sync", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"], name=op.f("fk_integration_jobs_started_by_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_jobs")),
    )
    op.create_index(op.f("ix_integration_jobs_started_by"), "integration_jobs", ["started_by"], unique=False)
    op.create_index(op.f("ix_integration_jobs_status"), "integration_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_integration_jobs_type"), "integration_jobs", ["type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_jobs_type"), table_name="integration_jobs")
    op.drop_index(op.f("ix_integration_jobs_status"), table_name="integration_jobs")
    op.drop_index(op.f("ix_integration_jobs_started_by"), table_name="integration_jobs")
    op.drop_table("integration_jobs")
