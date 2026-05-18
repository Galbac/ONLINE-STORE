from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.pickup_point import PickupPoint


class PickupPointRepository:
    async def get_by_id(self, *, session: AsyncSession, pickup_point_id: int) -> PickupPoint | None:
        result = await session.execute(select(PickupPoint).where(PickupPoint.id == pickup_point_id))
        return result.scalar_one_or_none()
