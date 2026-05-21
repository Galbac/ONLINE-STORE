from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.delivery_settings import DeliverySettings


class DeliverySettingsRepository:
    async def get(self, *, session: AsyncSession) -> DeliverySettings | None:
        return await self.get_settings(session=session)

    async def get_settings(self, *, session: AsyncSession) -> DeliverySettings | None:
        result = await session.execute(select(DeliverySettings).order_by(DeliverySettings.id.asc()).limit(1))
        return result.scalar_one_or_none()

    async def get_or_create_default(self, *, session: AsyncSession) -> tuple[DeliverySettings, bool]:
        delivery_settings = await self.get(session=session)
        if delivery_settings is not None:
            return delivery_settings, False

        delivery_settings = DeliverySettings(
            delivery_enabled=True,
            pickup_enabled=True,
            delivery_description="Доставка по городу",
            pickup_description="Самовывоз доступен из выбранных магазинов",
            default_city="Москва",
            currency="RUB",
        )
        session.add(delivery_settings)
        await session.flush()
        await session.refresh(delivery_settings)
        return delivery_settings, True

    async def update(
        self,
        *,
        session: AsyncSession,
        delivery_settings: DeliverySettings,
        data: dict,
    ) -> DeliverySettings:
        for field, value in data.items():
            setattr(delivery_settings, field, value)
        session.add(delivery_settings)
        await session.flush()
        await session.refresh(delivery_settings)
        return delivery_settings
