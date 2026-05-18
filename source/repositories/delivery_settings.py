from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.delivery_settings import DeliverySettings


class DeliverySettingsRepository:
    async def get_settings(self, *, session: AsyncSession) -> DeliverySettings | None:
        result = await session.execute(select(DeliverySettings).order_by(DeliverySettings.id.asc()).limit(1))
        return result.scalar_one_or_none()
