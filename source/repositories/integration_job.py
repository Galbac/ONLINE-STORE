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
