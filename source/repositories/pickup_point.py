from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.pickup_point import PickupPoint
from source.schemas.pydantic.delivery import AdminPickupPointCreateRequest, AdminPickupPointListQueryParams, PickupPointListQueryParams


class PickupPointRepository:
    async def get_by_city_and_address(
        self,
        *,
        session: AsyncSession,
        city: str,
        address: str,
    ) -> PickupPoint | None:
        result = await session.execute(
            select(PickupPoint)
            .where(
                func.lower(PickupPoint.city) == city.lower(),
                func.lower(PickupPoint.address) == address.lower(),
                PickupPoint.is_deleted.is_(False),
            )
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        session: AsyncSession,
        data: AdminPickupPointCreateRequest,
    ) -> PickupPoint:
        pickup_point = PickupPoint(
            name=data.name,
            city=data.city,
            address=data.address,
            working_hours=data.working_hours,
            phone=data.phone,
            description=data.description,
            latitude=data.latitude,
            longitude=data.longitude,
            is_active=data.is_active,
            sort_order=data.sort_order,
        )
        session.add(pickup_point)
        await session.flush()
        await session.refresh(pickup_point)
        return pickup_point

    async def update(
        self,
        *,
        session: AsyncSession,
        pickup_point: PickupPoint,
        data: dict,
    ) -> PickupPoint:
        for field, value in data.items():
            setattr(pickup_point, field, value)
        await session.flush()
        await session.refresh(pickup_point)
        return pickup_point

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        pickup_point: PickupPoint,
        deleted_by: int,
    ) -> PickupPoint:
        pickup_point.is_deleted = True
        pickup_point.is_active = False
        pickup_point.deleted_at = datetime.now(settings.tz)
        pickup_point.deleted_by = deleted_by
        session.add(pickup_point)
        await session.flush()
        await session.refresh(pickup_point)
        return pickup_point

    async def get_by_id(self, *, session: AsyncSession, pickup_point_id: int) -> PickupPoint | None:
        result = await session.execute(select(PickupPoint).where(PickupPoint.id == pickup_point_id))
        return result.scalar_one_or_none()

    async def get_active_by_id(self, *, session: AsyncSession, pickup_point_id: int) -> PickupPoint | None:
        result = await session.execute(
            select(PickupPoint).where(
                PickupPoint.id == pickup_point_id,
                PickupPoint.is_active.is_(True),
                PickupPoint.is_deleted.is_(False),
            ),
        )
        return result.scalar_one_or_none()

    async def has_active_points(self, *, session: AsyncSession) -> bool:
        result = await session.execute(
            select(func.count())
            .select_from(PickupPoint)
            .where(
                PickupPoint.is_active.is_(True),
                PickupPoint.is_deleted.is_(False),
            ),
        )
        return int(result.scalar_one()) > 0

    async def get_list(
        self,
        *,
        session: AsyncSession,
        query: PickupPointListQueryParams | AdminPickupPointListQueryParams,
    ) -> list[PickupPoint]:
        statement = self._base_statement(query=query)
        statement = statement.order_by(PickupPoint.sort_order.asc(), PickupPoint.name.asc()).limit(query.limit).offset(query.offset)
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        session: AsyncSession,
        query: PickupPointListQueryParams | AdminPickupPointListQueryParams,
    ) -> int:
        statement = self._base_statement(query=query, count=True)
        result = await session.execute(statement)
        return int(result.scalar_one())

    def _base_statement(self, *, query: PickupPointListQueryParams | AdminPickupPointListQueryParams, count: bool = False):
        statement = select(func.count(PickupPoint.id)) if count else select(PickupPoint)
        if isinstance(query, AdminPickupPointListQueryParams):
            if not query.include_deleted:
                statement = statement.where(PickupPoint.is_deleted.is_(False))
            if query.q is not None:
                search_pattern = f"%{query.q}%"
                statement = statement.where(
                    or_(
                        PickupPoint.name.ilike(search_pattern),
                        PickupPoint.address.ilike(search_pattern),
                        PickupPoint.city.ilike(search_pattern),
                    ),
                )
            if query.is_active is not None:
                statement = statement.where(PickupPoint.is_active.is_(query.is_active))
        else:
            statement = statement.where(PickupPoint.is_deleted.is_(False))
            if query.only_active:
                statement = statement.where(PickupPoint.is_active.is_(True))
        if query.city is not None:
            statement = statement.where(func.lower(PickupPoint.city) == query.city.lower())
        return statement
