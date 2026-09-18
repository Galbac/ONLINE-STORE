from sqlalchemy.ext.asyncio import AsyncSession

from source.common.commiter import Commiter
from source.repositories.feedback import FeedbackRepository
from source.schemas.pydantic.feedback import (
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackResponse,
)


class FeedbackService:
    async def create_feedback(
        self,
        *,
        session: AsyncSession,
        feedback_repository: FeedbackRepository,
        commiter: Commiter,
        data: FeedbackCreateRequest,
    ) -> FeedbackResponse:
        feedback = await feedback_repository.create(
            session=session,
            **data.model_dump(),
        )
        await commiter.commit()
        return FeedbackResponse.model_validate(feedback)

    async def get_all_feedbacks(
        self,
        *,
        session: AsyncSession,
        feedback_repository: FeedbackRepository,
        status: str | None = None,
    ) -> FeedbackListResponse:
        feedbacks = await feedback_repository.get_all(session=session, status=status)
        return FeedbackListResponse(
            items=[FeedbackResponse.model_validate(f) for f in feedbacks],
            total=len(feedbacks),
        )

    async def update_status(
        self,
        *,
        session: AsyncSession,
        feedback_repository: FeedbackRepository,
        commiter: Commiter,
        feedback_id: int,
        status: str,
    ) -> FeedbackResponse | None:
        feedback = await feedback_repository.get_by_id(session=session, feedback_id=feedback_id)
        if feedback is None:
            return None
        updated = await feedback_repository.update_status(
            session=session,
            feedback=feedback,
            status=status,
        )
        await commiter.commit()
        return FeedbackResponse.model_validate(updated)
