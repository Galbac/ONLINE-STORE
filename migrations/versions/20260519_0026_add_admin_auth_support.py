"""add admin auth support

Revision ID: 20260519_0026
Revises: 20260519_0025
Create Date: 2026-05-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260519_0026"
down_revision: str | None = "20260519_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'content_manager'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'picker'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'courier'")

    op.create_table(
        "admin_audit_logs",
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("ip_address", sa.String(length=100), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.text("timezone('Europe/Moscow', now())"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_admin_audit_logs_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_logs")),
    )
    op.create_index(op.f("ix_admin_audit_logs_user_id"), "admin_audit_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_admin_audit_logs_login"), "admin_audit_logs", ["login"], unique=False)
    op.create_index(op.f("ix_admin_audit_logs_event"), "admin_audit_logs", ["event"], unique=False)
    op.create_index(op.f("ix_admin_audit_logs_status"), "admin_audit_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_logs_status"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_event"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_login"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_user_id"), table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
