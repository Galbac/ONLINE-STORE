from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.pickup_point import PickupPoint
from source.schemas.pydantic.delivery import PickupPointListQueryParams


class PickupPointRepository:
    async def get_by_id(self, *, session: AsyncSession, pickup_point_id: int) -> PickupPoint | None:
        result = await session.execute(select(PickupPoint).where(PickupPoint.id == pickup_point_id))
        return result.scalar_one_or_none()

    async def get_active_by_id(self, *, session: AsyncSession, pickup_point_id: int) -> PickupPoint | None:
        result = await session.execute(
            select(PickupPoint).where(
                PickupPoint.id == pickup_point_id,
                PickupPoint.is_active.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def has_active_points(self, *, session: AsyncSession) -> bool:
        result = await session.execute(
            select(func.count())
            .select_from(PickupPoint)
            .where(PickupPoint.is_active.is_(True)),
        )
        return int(result.scalar_one()) > 0

    async def get_list(
        self,
        *,
        session: AsyncSession,
        query: PickupPointListQueryParams,
    ) -> list[PickupPoint]:
        statement = self._base_statement(query=query)
        statement = statement.order_by(PickupPoint.sort_order.asc(), PickupPoint.name.asc()).limit(query.limit).offset(query.offset)
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        session: AsyncSession,
        query: PickupPointListQueryParams,
    ) -> int:
        statement = self._base_statement(query=query, count=True)
        result = await session.execute(statement)
        return int(result.scalar_one())

    def _base_statement(self, *, query: PickupPointListQueryParams, count: bool = False):
        statement = select(func.count(PickupPoint.id)) if count else select(PickupPoint)
        if query.only_active:
            statement = statement.where(PickupPoint.is_active.is_(True))
        if query.city is not None:
            statement = statement.where(func.lower(PickupPoint.city) == query.city.lower())
        return statement
