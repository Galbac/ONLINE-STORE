from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product_availability_log import ProductAvailabilityLog


class ProductAvailabilityLogRepository:
    async def create(self, *, session: AsyncSession, **data) -> ProductAvailabilityLog:
        log = ProductAvailabilityLog(**data)
        session.add(log)
        await session.flush()
        await session.refresh(log)
        return log
