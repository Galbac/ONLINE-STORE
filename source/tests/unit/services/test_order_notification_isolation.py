from datetime import datetime, UTC
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from source.db.models.order import Order
from source.db.models.user import User
from source.db.models.choises.enum import UserRole
from source.schemas.pydantic.order import OrderCreateRequest
from source.services.order import OrderService


class FakeCommiter:
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


@pytest.mark.asyncio
async def test_order_creation_succeeds_even_if_notifications_fail():
    session = AsyncMock()
    commiter = FakeCommiter()
    redis_service = AsyncMock()
    cart_repo = AsyncMock()
    cart_item_repo = AsyncMock()
    product_repo = AsyncMock()
    address_repo = AsyncMock()
    pickup_repo = AsyncMock()
    promo_repo = AsyncMock()
    promo_usage_repo = AsyncMock()
    order_repo = AsyncMock()
    order_item_repo = AsyncMock()
    payment_repo = AsyncMock()

    cart_cache = AsyncMock()
    order_cache = AsyncMock()
    profile_cache = AsyncMock()
    product_cache = AsyncMock()
    delivery_cache = AsyncMock()

    cart_calc = MagicMock()
    stock_service = MagicMock()
    stock_service.validate_order_items.return_value = []
    stock_service.reserve_items = AsyncMock()
    delivery_service = MagicMock()
    payment_service = AsyncMock()
    one_c_service = AsyncMock()
    promo_code_service = AsyncMock()

    # Внешние сервисы уведомлений выбрасывают исключения (например, таймаут Telegram или SMTP)
    notification_service = AsyncMock()
    notification_service.notify_order_created.side_effect = ConnectionError("Telegram API timeout")

    email_service = AsyncMock()
    telegram_service = AsyncMock()
    telegram_service.send_message.side_effect = RuntimeError("Telegram network down")

    user = User(
        id=1,
        name="Тестовый Покупатель",
        phone="+79991234567",
        email="buyer@example.com",
        role=UserRole.CUSTOMER,
        is_active=True,
        telegram_chat_id="123456789",
    )

    cart = SimpleNamespace(id=1, user_id=1, promo_code_id=None)
    cart_repo.get_by_user_id.return_value = cart

    cart_item = SimpleNamespace(
        id=10,
        cart_id=1,
        product_id=100,
        quantity=Decimal("2"),
    )
    cart_item_repo.get_by_cart_id.return_value = [cart_item]

    product = SimpleNamespace(
        id=100,
        name="Хлеб Бородинский",
        slug="hleb-borodinskiy",
        price=Decimal("50.00"),
        old_price=None,
        stock_quantity=Decimal("10"),
        is_active=True,
        is_deleted=False,
        is_available=True,
        unit="шт",
        product_type="piece",
    )
    product_repo.get_by_ids.return_value = [product]
    stock_service.validate_order_items.return_value = []

    snapshot_item = SimpleNamespace(
        product_id=100,
        discount_amount=Decimal("0.00"),
        total_price=Decimal("100.00"),
        final_price=Decimal("100.00"),
    )
    cart_calc.calculate.return_value = SimpleNamespace(
        items=[snapshot_item],
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
    )
    delivery_service.calculate_delivery_price.return_value = Decimal("150.00")

    created_order = Order(
        id=555,
        order_number="ORD-555",
        user_id=1,
        status="pending",
        payment_method="on_delivery",
        payment_status="unpaid",
        delivery_type="pickup",
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
        delivery_price=Decimal("150.00"),
        final_price=Decimal("250.00"),
        customer_name="Тестовый Покупатель",
        customer_phone="+79991234567",
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    order_repo.create.return_value = created_order
    pickup_repo.get_by_id.return_value = SimpleNamespace(id=1, is_active=True)

    service = OrderService()
    request_data = OrderCreateRequest(
        delivery_type="pickup",
        pickup_point_id=1,
        payment_method="on_delivery",
        customer_name="Тестовый Покупатель",
        customer_phone="+79991234567",
    )

    response = await service.create_order(
        session=session,
        commiter=commiter,
        redis_service=redis_service,
        cart_repository=cart_repo,
        cart_item_repository=cart_item_repo,
        product_repository=product_repo,
        address_repository=address_repo,
        pickup_point_repository=pickup_repo,
        promo_code_repository=promo_repo,
        promo_code_usage_repository=promo_usage_repo,
        order_repository=order_repo,
        order_item_repository=order_item_repo,
        payment_repository=payment_repo,
        cart_cache_service=cart_cache,
        order_cache_service=order_cache,
        profile_cache_service=profile_cache,
        product_cache_service=product_cache,
        delivery_cache_service=delivery_cache,
        cart_calculator_service=cart_calc,
        stock_service=stock_service,
        delivery_service=delivery_service,
        promo_code_service=promo_code_service,
        notification_service=notification_service,
        email_service=email_service,
        telegram_service=telegram_service,
        payment_service=payment_service,
        one_c_integration_service=one_c_service,
        user=user,
        data=request_data,
    )

    assert response.id == 555
    assert response.order_number == "ORD-000555"
    assert response.final_price == Decimal("250.00")
