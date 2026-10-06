from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.search_query_stat import SearchQueryStat


class SearchQueryStatRepository:
    async def track(self, *, session: AsyncSession, query: str, today: date) -> None:
        await session.execute(
            delete(SearchQueryStat).where(SearchQueryStat.search_date < today - timedelta(days=29)),
        )
        statement = insert(SearchQueryStat).values(
            search_date=today,
            query=query,
            search_count=1,
        )
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_search_query_stats_date_query",
                set_={"search_count": SearchQueryStat.search_count + 1},
            ),
        )
        await session.commit()

    async def get_popular(self, *, session: AsyncSession, today: date, limit: int = 8) -> list[str]:
        result = await session.scalars(
            select(SearchQueryStat.query)
            .where(SearchQueryStat.search_date >= today - timedelta(days=29))
            .group_by(SearchQueryStat.query)
            .having(func.sum(SearchQueryStat.search_count) >= 2)
            .order_by(func.sum(SearchQueryStat.search_count).desc(), SearchQueryStat.query.asc())
            .limit(limit),
        )
        return list(result.all())
