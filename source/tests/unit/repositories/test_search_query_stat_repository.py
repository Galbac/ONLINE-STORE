from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from source.repositories.search_query_stat import SearchQueryStatRepository


@pytest.mark.asyncio
async def test_track_upserts_daily_count_and_prunes_old_rows() -> None:
    class RecordingSession:
        def __init__(self):
            self.statements = []
            self.committed = False

        async def execute(self, statement):
            self.statements.append(statement)

        async def commit(self):
            self.committed = True

    session = RecordingSession()
    repository = SearchQueryStatRepository()

    await repository.track(session=session, query="овощи", today=date(2026, 10, 6))

    assert len(session.statements) == 2
    assert session.committed is True
    upsert = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_search_query_stats_date_query" in upsert
    assert "search_count = (search_query_stats.search_count + %(search_count_1)s)" in upsert


@pytest.mark.asyncio
async def test_popular_queries_only_returns_recent_aggregated_terms() -> None:
    result = MagicMock()
    result.all.return_value = ["овощи", "молоко"]

    class ScalarSession:
        statement = None

        async def scalars(self, statement):
            self.statement = statement
            return result

    session = ScalarSession()
    repository = SearchQueryStatRepository()

    popular = await repository.get_popular(session=session, today=date(2026, 10, 6), limit=8)

    assert popular == ["овощи", "молоко"]
    statement = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "HAVING sum(search_query_stats.search_count) >=" in statement
    assert "LIMIT" in statement
