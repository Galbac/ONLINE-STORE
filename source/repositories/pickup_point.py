from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.pickup_point import PickupPoint


class PickupPointRepository:
    async def get_by_id(self, *, session: AsyncSession, pickup_point_id: int) -> PickupPoint | None:
        result = await session.execute(select(PickupPoint).where(PickupPoint.id == pickup_point_id))
        return result.scalar_one_or_none()

    async def has_active_points(self, *, session: AsyncSession) -> bool:
        result = await session.execute(
            select(func.count())
            .select_from(PickupPoint)
            .where(PickupPoint.is_active.is_(True)),
        )
        return int(result.scalar_one()) > 0
