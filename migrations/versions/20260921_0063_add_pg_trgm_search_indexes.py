"""add pg_trgm extension and product search trigram gin indexes

Revision ID: 20260921_0063
Revises: 20260921_0062
Create Date: 2026-09-21 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260921_0063'
down_revision: Union[str, None] = '20260921_0062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Безопасное подключение расширения pg_trgm для ускорения ILIKE и fuzzy-поиска
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_name_trgm "
        "ON products USING gin (name gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_search_keywords_trgm "
        "ON products USING gin (search_keywords gin_trgm_ops);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_search_keywords_trgm;")
    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm;")
