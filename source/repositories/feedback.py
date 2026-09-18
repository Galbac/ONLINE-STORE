from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.feedback import Feedback


class FeedbackRepository:
    async def get_all(
        self,
        *,
        session: AsyncSession,
        status: str | None = None,
    ) -> list[Feedback]:
        stmt = select(Feedback)
        if status:
            stmt = stmt.where(Feedback.status == status)
        stmt = stmt.order_by(desc(Feedback.created_date))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, *, session: AsyncSession, feedback_id: int) -> Feedback | None:
        stmt = select(Feedback).where(Feedback.id == feedback_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, session: AsyncSession, **kwargs) -> Feedback:
        feedback = Feedback(**kwargs)
        session.add(feedback)
        await session.flush()
        await session.refresh(feedback)
        return feedback

    async def update_status(
        self,
        *,
        session: AsyncSession,
        feedback: Feedback,
        status: str,
    ) -> Feedback:
        feedback.status = status
        session.add(feedback)
        await session.flush()
        await session.refresh(feedback)
        return feedback
