from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import require_admin_or_manager
from source.common.commiter import Commiter
from source.db.models.user import User
from source.repositories.feedback import FeedbackRepository
from source.schemas.pydantic.feedback import (
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackReplyRequest,
    FeedbackResponse,
    FeedbackStatusUpdateRequest,
)
from source.services.feedback import FeedbackService
from source.services.notifications import EmailService

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
@inject
async def submit_feedback(
    body: FeedbackCreateRequest,
    session: FromDishka[AsyncSession] = None,
    feedback_repository: FromDishka[FeedbackRepository] = None,
    feedback_service: FromDishka[FeedbackService] = None,
    commiter: FromDishka[Commiter] = None,
) -> FeedbackResponse:
    return await feedback_service.create_feedback(
        session=session,
        feedback_repository=feedback_repository,
        commiter=commiter,
        data=body,
    )


@router.get("/admin/feedback", response_model=FeedbackListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_feedbacks(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    feedback_repository: FromDishka[FeedbackRepository] = None,
    feedback_service: FromDishka[FeedbackService] = None,
) -> FeedbackListResponse:
    return await feedback_service.get_all_feedbacks(
        session=session,
        feedback_repository=feedback_repository,
        status=status_filter,
    )


@router.patch("/admin/feedback/{feedback_id}/status", response_model=FeedbackResponse, status_code=status.HTTP_200_OK)
@inject
async def update_feedback_status(
    feedback_id: int,
    body: FeedbackStatusUpdateRequest,
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    feedback_repository: FromDishka[FeedbackRepository] = None,
    feedback_service: FromDishka[FeedbackService] = None,
    commiter: FromDishka[Commiter] = None,
) -> FeedbackResponse:
    feedback = await feedback_service.update_status(
        session=session,
        feedback_repository=feedback_repository,
        commiter=commiter,
        feedback_id=feedback_id,
        status=body.status,
    )
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")
    return feedback


@router.post("/admin/feedback/{feedback_id}/reply", response_model=FeedbackResponse, status_code=status.HTTP_200_OK)
@inject
async def reply_to_feedback(
    feedback_id: int,
    body: FeedbackReplyRequest,
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    feedback_repository: FromDishka[FeedbackRepository] = None,
    feedback_service: FromDishka[FeedbackService] = None,
    email_service: FromDishka[EmailService] = None,
    commiter: FromDishka[Commiter] = None,
) -> FeedbackResponse:
    feedback = await feedback_repository.get_by_id(session=session, feedback_id=feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")

    if feedback.email:
        try:
            await email_service.send_email(
                to_email=feedback.email,
                subject=f"Ответ на ваше обращение: {feedback.subject}",
                text=body.message,
            )
        except Exception:
            pass

    updated = await feedback_service.update_status(
        session=session,
        feedback_repository=feedback_repository,
        commiter=commiter,
        feedback_id=feedback_id,
        status="resolved",
    )
    return updated
