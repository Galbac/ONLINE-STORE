from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.integration_log import IntegrationLog


class IntegrationLogRepository:
    async def create(self, *, session: AsyncSession, **data) -> IntegrationLog:
        log = IntegrationLog(**data)
        session.add(log)
        await session.flush()
        await session.refresh(log)
        return log
