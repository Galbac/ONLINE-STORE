from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.delivery_zone import DeliveryZone


class DeliveryZoneRepository:
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
            )
            .order_by(DeliveryZone.id.asc())
            .limit(1),
        )
        return result.scalar_one_or_none()
