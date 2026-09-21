from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.feedback import (
    get_admin_feedbacks,
    reply_to_feedback,
    submit_feedback,
    update_feedback_status,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.schemas.pydantic.feedback import (
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackReplyRequest,
    FeedbackResponse,
    FeedbackStatusUpdateRequest,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def admin_user():
    return User(id=1, name="Администратор", role=UserRole.ADMIN, is_active=True)


@pytest.fixture
def fake_feedback():
    now = datetime.now(UTC)
    return FeedbackResponse(
        id=1,
        name="Клиент",
        email="client@example.com",
        phone="+79991234567",
        order_number="ORD-123456",
        subject="Вопрос по доставке",
        message="Когда приедет заказ?",
        status="new",
        created_date=now,
    )


# ---------------------------------------------------------
# POST /feedback
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_feedback_success(fake_feedback):
    service = AsyncMock()
    service.create_feedback.return_value = fake_feedback

    body = FeedbackCreateRequest(
        name="Клиент",
        email="client@example.com",
        phone="+79991234567",
        order_number="ORD-123456",
        subject="Вопрос по доставке",
        message="Когда приедет заказ?",
    )

    response = await unwrap(submit_feedback)(
        body=body,
        session=AsyncMock(),
        feedback_repository=AsyncMock(),
        feedback_service=service,
        commiter=AsyncMock(),
    )

    assert response.id == 1
    assert response.status == "new"
    assert response.subject == "Вопрос по доставке"


# ---------------------------------------------------------
# GET /admin/feedback
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_admin_feedbacks_success(admin_user, fake_feedback):
    service = AsyncMock()
    service.get_all_feedbacks.return_value = FeedbackListResponse(
        items=[fake_feedback],
        total=1,
    )

    response = await unwrap(get_admin_feedbacks)(
        status_filter="new",
        current_user=admin_user,
        session=AsyncMock(),
        feedback_repository=AsyncMock(),
        feedback_service=service,
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].email == "client@example.com"


# ---------------------------------------------------------
# PATCH /admin/feedback/{feedback_id}/status
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_update_feedback_status_success(admin_user, fake_feedback):
    service = AsyncMock()
    fake_feedback_in_progress = fake_feedback.model_copy(update={"status": "in_progress"})
    service.update_status.return_value = fake_feedback_in_progress

    body = FeedbackStatusUpdateRequest(status="in_progress")
    response = await unwrap(update_feedback_status)(
        feedback_id=1,
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        feedback_repository=AsyncMock(),
        feedback_service=service,
        commiter=AsyncMock(),
    )

    assert response.status == "in_progress"


@pytest.mark.asyncio
async def test_update_feedback_status_not_found(admin_user):
    service = AsyncMock()
    service.update_status.return_value = None

    body = FeedbackStatusUpdateRequest(status="resolved")
    with pytest.raises(HTTPException) as exc:
        await unwrap(update_feedback_status)(
            feedback_id=999,
            body=body,
            current_user=admin_user,
            session=AsyncMock(),
            feedback_repository=AsyncMock(),
            feedback_service=service,
            commiter=AsyncMock(),
        )
    assert exc.value.status_code == 404
    assert "не найдено" in exc.value.detail.lower()


# ---------------------------------------------------------
# POST /admin/feedback/{feedback_id}/reply
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_reply_to_feedback_success(admin_user, fake_feedback):
    repo = AsyncMock()
    feedback_entity = SimpleNamespace(
        id=1,
        email="client@example.com",
        subject="Вопрос по доставке",
    )
    repo.get_by_id.return_value = feedback_entity

    service = AsyncMock()
    fake_feedback_resolved = fake_feedback.model_copy(update={"status": "resolved"})
    service.update_status.return_value = fake_feedback_resolved

    email_service = AsyncMock()
    body = FeedbackReplyRequest(message="Курьер прибудет в 14:00")

    response = await unwrap(reply_to_feedback)(
        feedback_id=1,
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        feedback_repository=repo,
        feedback_service=service,
        email_service=email_service,
        commiter=AsyncMock(),
    )

    assert response.status == "resolved"
    assert email_service.send_email.called


@pytest.mark.asyncio
async def test_reply_to_feedback_not_found(admin_user):
    repo = AsyncMock()
    repo.get_by_id.return_value = None

    body = FeedbackReplyRequest(message="Ответ")
    with pytest.raises(HTTPException) as exc:
        await unwrap(reply_to_feedback)(
            feedback_id=999,
            body=body,
            current_user=admin_user,
            session=AsyncMock(),
            feedback_repository=repo,
            feedback_service=AsyncMock(),
            email_service=AsyncMock(),
            commiter=AsyncMock(),
        )
    assert exc.value.status_code == 404
