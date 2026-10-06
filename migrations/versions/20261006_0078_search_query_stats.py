"""Store anonymized daily search query counts."""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0078"
down_revision = "20261005_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_query_stats",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("search_date", sa.Date(), nullable=False),
        sa.Column("query", sa.String(length=80), nullable=False),
        sa.Column("search_count", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("search_date", "query", name="uq_search_query_stats_date_query"),
    )
    op.create_index("ix_search_query_stats_search_date", "search_query_stats", ["search_date"])


def downgrade() -> None:
    op.drop_index("ix_search_query_stats_search_date", table_name="search_query_stats")
    op.drop_table("search_query_stats")
