from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.delivery_zone import DeliveryZone
from source.schemas.pydantic.delivery import AdminDeliveryZoneCreateRequest, AdminDeliveryZoneListQueryParams


class DeliveryZoneRepository:
    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        zone_id: int,
    ) -> DeliveryZone | None:
        result = await session.execute(select(DeliveryZone).where(DeliveryZone.id == zone_id))
        return result.scalar_one_or_none()

    async def get_by_name_and_city(
        self,
        *,
        session: AsyncSession,
        name: str,
        city: str,
    ) -> DeliveryZone | None:
        result = await session.execute(
            select(DeliveryZone)
            .where(
                func.lower(DeliveryZone.name) == name.lower(),
                func.lower(DeliveryZone.city) == city.lower(),
                DeliveryZone.is_deleted.is_(False),
            )
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        session: AsyncSession,
        data: AdminDeliveryZoneCreateRequest,
    ) -> DeliveryZone:
        zone = DeliveryZone(
            name=data.name,
            city=data.city,
            description=data.description,
            delivery_price=data.delivery_price,
            free_delivery_from=data.free_delivery_from,
            min_order_amount=data.min_order_amount,
            is_active=data.is_active,
            sort_order=data.sort_order,
        )
        session.add(zone)
        await session.flush()
        await session.refresh(zone)
        return zone

    async def update(
        self,
        *,
        session: AsyncSession,
        zone: DeliveryZone,
        data: dict,
    ) -> DeliveryZone:
        for field, value in data.items():
            setattr(zone, field, value)
        await session.flush()
        await session.refresh(zone)
        return zone

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        zone: DeliveryZone,
        deleted_by: int,
    ) -> DeliveryZone:
        zone.is_deleted = True
        zone.is_active = False
        zone.deleted_at = datetime.now(settings.tz)
        zone.deleted_by = deleted_by
        session.add(zone)
        await session.flush()
        await session.refresh(zone)
        return zone

    def _admin_statement(self, *, query: AdminDeliveryZoneListQueryParams):
        statement = select(DeliveryZone)
        if not query.include_deleted:
            statement = statement.where(DeliveryZone.is_deleted.is_(False))
        if query.q is not None:
            search_pattern = f"%{query.q}%"
            statement = statement.where(
                or_(
                    DeliveryZone.name.ilike(search_pattern),
                    DeliveryZone.city.ilike(search_pattern),
                    DeliveryZone.description.ilike(search_pattern),
                ),
            )
        if query.city is not None:
            statement = statement.where(func.lower(DeliveryZone.city) == query.city.lower())
        if query.is_active is not None:
            statement = statement.where(DeliveryZone.is_active.is_(query.is_active))
        return statement

    async def get_list(
        self,
        *,
        session: AsyncSession,
        query: AdminDeliveryZoneListQueryParams,
    ) -> list[DeliveryZone]:
        result = await session.execute(
            self._admin_statement(query=query)
            .order_by(DeliveryZone.sort_order.asc(), DeliveryZone.name.asc())
            .limit(query.limit)
            .offset(query.offset),
        )
        return list(result.scalars().all())

    async def count(
        self,
        *,
        session: AsyncSession,
        query: AdminDeliveryZoneListQueryParams,
    ) -> int:
        zones_subquery = self._admin_statement(query=query).subquery()
        result = await session.execute(select(func.count()).select_from(zones_subquery))
        return int(result.scalar_one())

    async def find_by_city(
        self,
        *,
        session: AsyncSession,
        city: str,
    ) -> DeliveryZone | None:
        result = await session.execute(
            select(DeliveryZone)
            .where(
                func.lower(DeliveryZone.city) == city.lower(),
                DeliveryZone.is_active.is_(True),
                DeliveryZone.is_deleted.is_(False),
            )
            .order_by(DeliveryZone.id.asc())
            .limit(1),
        )
        return result.scalar_one_or_none()
