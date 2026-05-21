from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.store_settings import StoreSettings


class SettingsRepository:
    async def get(self, *, session: AsyncSession) -> StoreSettings | None:
        result = await session.execute(select(StoreSettings).order_by(StoreSettings.id.asc()).limit(1))
        return result.scalar_one_or_none()

    async def get_or_create_default(self, *, session: AsyncSession) -> tuple[StoreSettings, bool]:
        store_settings = await self.get(session=session)
        if store_settings is not None:
            return store_settings, False

        store_settings = StoreSettings()
        session.add(store_settings)
        await session.flush()
        await session.refresh(store_settings)
        return store_settings, True

    async def update(
        self,
        *,
        session: AsyncSession,
        store_settings: StoreSettings,
        data: dict,
    ) -> StoreSettings:
        for field, value in data.items():
            setattr(store_settings, field, value)
        session.add(store_settings)
        await session.flush()
        await session.refresh(store_settings)
        return store_settings
