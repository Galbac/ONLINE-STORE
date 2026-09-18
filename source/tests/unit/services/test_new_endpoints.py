import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, UTC

from source.db.models.choises.enum import UserRole
from source.db.models.order import Order
from source.db.models.order_status_history import OrderStatusHistory
from source.db.models.user import User
from source.db.models.banner import Banner
from source.db.models.product_review import ProductReview
from source.db.models.feedback import Feedback
from source.schemas.pydantic.banner import BannerCreateRequest, BannerUpdateRequest
from source.schemas.pydantic.review import ReviewCreateRequest
from source.schemas.pydantic.feedback import FeedbackCreateRequest
from source.services.banner import BannerService
from source.services.review import ReviewService
from source.services.feedback import FeedbackService
from source.services.loyalty import LoyaltyService
from source.services.order_tracking import OrderTrackingService


@pytest.mark.asyncio
async def test_banner_service():
    session = AsyncMock()
    commiter = AsyncMock()
    repo = AsyncMock()

    banner = Banner(
        id=1,
        title="Свежие фрукты",
        subtitle="Скидки до 30%",
        badge="Акция",
        image_url=None,
        link="/catalog",
        bg_color="#059669",
        sort_order=1,
        is_active=True,
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    repo.get_active_banners.return_value = [banner]
    repo.create.return_value = banner

    service = BannerService()
    active = await service.get_active_banners(session=session, banner_repository=repo)
    assert active.total == 1
    assert active.items[0].title == "Свежие фрукты"

    created = await service.create_banner(
        session=session,
        banner_repository=repo,
        commiter=commiter,
        data=BannerCreateRequest(title="Новый баннер"),
    )
    assert created.title == "Свежие фрукты"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_review_service():
    session = AsyncMock()
    commiter = AsyncMock()
    repo = AsyncMock()
    product_repo = AsyncMock()

    user = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)
    review = ProductReview(
        id=1,
        product_id=10,
        user_id=1,
        rating=5,
        text="Отличный товар!",
        pros="Свежий",
        cons=None,
        is_approved=True,
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    review.user = user
    repo.get_by_product.return_value = [review]
    repo.create.return_value = review

    service = ReviewService()
    reviews = await service.get_product_reviews(session=session, review_repository=repo, product_id=10)
    assert reviews.total == 1
    assert reviews.average_rating == 5.0

    created = await service.create_review(
        session=session,
        review_repository=repo,
        product_repository=product_repo,
        commiter=commiter,
        user=user,
        product_id=10,
        data=ReviewCreateRequest(rating=5, text="Супер!"),
    )
    assert created.rating == 5


@pytest.mark.asyncio
async def test_feedback_service():
    session = AsyncMock()
    commiter = AsyncMock()
    repo = AsyncMock()

    feedback = Feedback(
        id=1,
        name="Анна",
        email="anna@example.com",
        phone=None,
        subject="Вопрос по доставке",
        message="Когда будет доступна экспресс-доставка?",
        order_id=None,
        status="new",
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    repo.get_all.return_value = [feedback]
    repo.create.return_value = feedback

    service = FeedbackService()
    result = await service.get_all_feedbacks(session=session, feedback_repository=repo)
    assert result.total == 1

    created = await service.create_feedback(
        session=session,
        feedback_repository=repo,
        commiter=commiter,
        data=FeedbackCreateRequest(name="Анна", subject="Тест", message="Привет"),
    )
    assert created.name == "Анна"


@pytest.mark.asyncio
async def test_order_tracking_service():
    session = AsyncMock()
    order_repo = AsyncMock()
    history_repo = AsyncMock()

    user = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)
    order = Order(
        id=100,
        order_number="ORD-100",
        user_id=1,
        status="assembling",
        payment_status="paid",
        delivery_type="delivery",
        final_price=1500,
        customer_name="Иван",
        customer_phone="+79990000000",
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    order_repo.get_by_id.return_value = order

    history = [
        OrderStatusHistory(order_id=100, status="created", created_date=datetime.now(UTC)),
        OrderStatusHistory(order_id=100, status="confirmed", created_date=datetime.now(UTC)),
        OrderStatusHistory(order_id=100, status="assembling", created_date=datetime.now(UTC)),
    ]
    history_repo.get_by_order_id.return_value = history

    service = OrderTrackingService()
    tracking = await service.get_tracking(
        session=session,
        order_repository=order_repo,
        order_status_history_repository=history_repo,
        user=user,
        order_id=100,
    )
    assert tracking is not None
    assert tracking.order_number == "ORD-100"
    assert tracking.current_status == "assembling"
    assert len(tracking.steps) == 5
    # Steps: created (completed), confirmed (completed), assembling (current & completed)
    assert tracking.steps[0].is_completed is True
    assert tracking.steps[2].is_current is True
    assert tracking.steps[3].is_completed is False


@pytest.mark.asyncio
async def test_loyalty_service():
    session = AsyncMock()
    commiter = AsyncMock()
    repo = AsyncMock()

    user = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)
    from source.db.models.loyalty import LoyaltyAccount, LoyaltyTransaction
    account = LoyaltyAccount(id=1, user_id=1, balance=500)
    repo.get_or_create_account.return_value = account
    repo.get_transactions.return_value = [
        LoyaltyTransaction(id=1, user_id=1, amount=100, transaction_type="accrual", description="Бонус", created_date=datetime.now(UTC))
    ]

    service = LoyaltyService()
    info = await service.get_loyalty_info(session=session, loyalty_repository=repo, user=user)
    assert info.balance == 500
    assert info.level == "Серебряный"
    assert info.cashback_percent == 5
    assert len(info.transactions) == 1

    await service.accrue_points(
        session=session,
        loyalty_repository=repo,
        commiter=commiter,
        user_id=1,
        amount=50,
        description="Кэшбэк",
    )
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_telegram_connect_service():
    redis_service = AsyncMock()
    user = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True, telegram_chat_id=None)

    from source.services.telegram_connect import TelegramConnectService
    service = TelegramConnectService()
    connect = await service.create_connect_token(redis_service=redis_service, user=user)
    assert connect.is_connected is False
    assert connect.token != ""
    assert "t.me" in connect.connect_url

    status = await service.get_status(user=user)
    assert status.is_connected is False
