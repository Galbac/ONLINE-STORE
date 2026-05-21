from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.integration_job import IntegrationJob


class IntegrationJobRepository:
    async def create(self, *, session: AsyncSession, **data) -> IntegrationJob:
        job = IntegrationJob(**data)
        session.add(job)
        await session.flush()
        await session.refresh(job)
        return job

    async def update_status(self, *, session: AsyncSession, job: IntegrationJob, **data) -> IntegrationJob:
        for field, value in data.items():
            setattr(job, field, value)
        await session.flush()
        await session.refresh(job)
        return job

    async def count_active(self, *, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(IntegrationJob.id)).where(IntegrationJob.status == "started"),
        )
        return int(result.scalar_one() or 0)
