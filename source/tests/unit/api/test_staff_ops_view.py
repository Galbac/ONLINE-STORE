import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime, UTC
from fastapi import HTTPException, status

from source.db.models.choises.enum import UserRole
from source.db.models.feedback import Feedback
from source.db.models.order import Order
from source.db.models.product_review import ProductReview
from source.db.models.user import User
from source.schemas.pydantic.feedback import FeedbackCreateRequest, FeedbackReplyRequest
from source.schemas.pydantic.review import ReviewModerateRequest
from source.api.api_v1.views.feedback import (
    get_admin_feedbacks,
    reply_to_feedback,
    submit_feedback,
)
from source.api.api_v1.views.reviews import (
    get_admin_reviews,
    moderate_review,
)
from source.api.api_v1.views.staff_ops import (
    complete_order_assembly,
    export_orders_csv,
    export_products_csv,
    get_courier_orders_queue,
    get_orders_for_assembly,
    mark_order_delivered,
    start_order_assembly,
    take_order_delivery,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_assembly_workflow():
    session = AsyncMock()
    order_repo = AsyncMock()
    history_repo = AsyncMock()
    commiter = AsyncMock()

    picker = User(id=10, name="Сборщик Вася", role=UserRole.PICKER, is_active=True)
    order = Order(
        id=1,
        order_number="ORD-001",
        status="paid",
        customer_name="Иван",
        customer_phone="+79990000000",
        final_price=Decimal("1000.00"),
        delivery_type="delivery",
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    order_repo.get_by_id.return_value = order

    # Start assembly
    res_start = await unwrap(start_order_assembly)(
        order_id=1,
        current_user=picker,
        session=session,
        order_repository=order_repo,
        order_status_history_repository=history_repo,
        commiter=commiter,
    )
    assert res_start.status == "assembling"
    assert history_repo.create.called
    assert commiter.commit.called

    # Complete assembly
    res_complete = await unwrap(complete_order_assembly)(
        order_id=1,
        current_user=picker,
        session=session,
        order_repository=order_repo,
        order_status_history_repository=history_repo,
        commiter=commiter,
    )
    assert res_complete.status == "assembled"


@pytest.mark.asyncio
async def test_courier_workflow_with_notifications_and_cashback():
    session = AsyncMock()
    order_repo = AsyncMock()
    history_repo = AsyncMock()
    loyalty_repo = AsyncMock()
    loyalty_service = AsyncMock()
    telegram_service = AsyncMock()
    commiter = AsyncMock()

    courier = User(id=20, name="Курьер Петя", role=UserRole.COURIER, is_active=True)
    customer = User(id=30, name="Покупатель", role=UserRole.CUSTOMER, is_active=True, telegram_chat_id="123456")
    order = Order(
        id=2,
        order_number="ORD-002",
        user_id=30,
        status="assembled",
        customer_name="Покупатель",
        customer_phone="+79990000000",
        final_price=Decimal("2000.00"),
        delivery_type="delivery",
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    order_repo.get_by_id.return_value = order
    session.get.return_value = customer

    # Take delivery
    res_take = await unwrap(take_order_delivery)(
        order_id=2,
        current_user=courier,
        session=session,
        order_repository=order_repo,
        order_status_history_repository=history_repo,
        telegram_service=telegram_service,
        commiter=commiter,
    )
    assert res_take.status == "in_delivery"
    assert telegram_service.send_message.called

    # Mark delivered
    res_deliv = await unwrap(mark_order_delivered)(
        order_id=2,
        current_user=courier,
        session=session,
        order_repository=order_repo,
        order_status_history_repository=history_repo,
        loyalty_repository=loyalty_repo,
        loyalty_service=loyalty_service,
        telegram_service=telegram_service,
        commiter=commiter,
    )
    assert res_deliv.status == "delivered"
    assert loyalty_service.accrue_points.called
    assert telegram_service.send_message.called


@pytest.mark.asyncio
async def test_feedback_and_reply():
    session = AsyncMock()
    feedback_repo = AsyncMock()
    feedback_service = AsyncMock()
    email_service = AsyncMock()
    commiter = AsyncMock()
    admin = User(id=1, name="Админ", role=UserRole.ADMIN, is_active=True)

    feedback = Feedback(
        id=5,
        name="Клиент",
        email="client@example.com",
        subject="Вопрос",
        message="Где мой заказ?",
        status="new",
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    feedback_repo.get_by_id.return_value = feedback

    # Reply to feedback
    await unwrap(reply_to_feedback)(
        feedback_id=5,
        body=FeedbackReplyRequest(message="Ваш заказ уже в пути!"),
        current_user=admin,
        session=session,
        feedback_repository=feedback_repo,
        feedback_service=feedback_service,
        email_service=email_service,
        commiter=commiter,
    )
    assert email_service.send_email.called
    assert feedback_service.update_status.called


@pytest.mark.asyncio
async def test_reviews_moderation():
    session = AsyncMock()
    review_repo = AsyncMock()
    review_service = AsyncMock()
    commiter = AsyncMock()
    admin = User(id=1, name="Админ", role=UserRole.ADMIN, is_active=True)

    # Moderate review
    await unwrap(moderate_review)(
        review_id=10,
        body=ReviewModerateRequest(is_approved=True),
        current_user=admin,
        session=session,
        review_repository=review_repo,
        review_service=review_service,
        commiter=commiter,
    )
    assert review_service.moderate_review.called


@pytest.mark.asyncio
async def test_csv_exports():
    session = AsyncMock()
    admin = User(id=1, name="Админ", role=UserRole.ADMIN, is_active=True)

    # Mock empty query results
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute.return_value = result_mock

    # Orders CSV
    orders_csv = await unwrap(export_orders_csv)(current_user=admin, session=session)
    assert orders_csv.media_type == "text/csv"
    assert "orders_export.csv" in orders_csv.headers["Content-Disposition"]

    # Products CSV
    products_csv = await unwrap(export_products_csv)(current_user=admin, session=session)
    assert products_csv.media_type == "text/csv"
    assert "products_export.csv" in products_csv.headers["Content-Disposition"]
