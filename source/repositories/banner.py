from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.banner import Banner


class BannerRepository:
    async def get_active_banners(self, *, session: AsyncSession) -> list[Banner]:
        stmt = (
            select(Banner)
            .where(Banner.is_active.is_(True))
            .order_by(Banner.sort_order.asc(), desc(Banner.id))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self, *, session: AsyncSession) -> list[Banner]:
        stmt = select(Banner).order_by(Banner.sort_order.asc(), desc(Banner.id))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, *, session: AsyncSession, banner_id: int) -> Banner | None:
        stmt = select(Banner).where(Banner.id == banner_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, session: AsyncSession, **kwargs) -> Banner:
        banner = Banner(**kwargs)
        session.add(banner)
        await session.flush()
        await session.refresh(banner)
        return banner

    async def update(self, *, session: AsyncSession, banner: Banner, **kwargs) -> Banner:
        for key, value in kwargs.items():
            if value is not None:
                setattr(banner, key, value)
        session.add(banner)
        await session.flush()
        await session.refresh(banner)
        return banner

    async def delete(self, *, session: AsyncSession, banner: Banner) -> None:
        await session.delete(banner)
        await session.flush()
