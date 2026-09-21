from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from source.db.models.choises.enum import UserRole
from source.db.models.order import Order
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    OrderAccessDeniedError,
    OrderItemsNotFoundError,
    OrderNotFoundError,
)
from source.schemas.pydantic.cart import CartResponse
from source.schemas.pydantic.order import RepeatOrderRequest
from source.services.order import OrderService


def make_fake_cart_response() -> CartResponse:
    return CartResponse(
        id=5,
        items=[],
        promo_code=None,
        items_count=1,
        total_quantity=Decimal("1"),
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
        delivery_price=None,
        final_price=Decimal("100.00"),
        warnings=[],
    )


@pytest.fixture
def base_user():
    return User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True, is_deleted=False)


@pytest.fixture
def base_order():
    return Order(id=10, order_number="ORD-10", user_id=1, status="delivered")


@pytest.mark.asyncio
async def test_repeat_order_user_inactive_error(base_order):
    user = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=False)
    service = OrderService()

    with pytest.raises(InactiveUserError):
        await service.repeat_order(
            session=AsyncMock(),
            redis_service=AsyncMock(),
            user=user,
            order_id=10,
            data=RepeatOrderRequest(replace_cart=False),
            order_repository=AsyncMock(),
            order_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            cart_service=AsyncMock(),
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
        )


@pytest.mark.asyncio
async def test_repeat_order_not_found_error(base_user):
    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = None
    service = OrderService()

    with pytest.raises(OrderNotFoundError):
        await service.repeat_order(
            session=AsyncMock(),
            redis_service=AsyncMock(),
            user=base_user,
            order_id=999,
            data=RepeatOrderRequest(replace_cart=False),
            order_repository=order_repo,
            order_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            cart_service=AsyncMock(),
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
        )


@pytest.mark.asyncio
async def test_repeat_order_access_denied_error(base_user):
    order_repo = AsyncMock()
    foreign_order = Order(id=10, order_number="ORD-10", user_id=999)
    order_repo.get_by_id.return_value = foreign_order
    service = OrderService()

    with pytest.raises(OrderAccessDeniedError):
        await service.repeat_order(
            session=AsyncMock(),
            redis_service=AsyncMock(),
            user=base_user,
            order_id=10,
            data=RepeatOrderRequest(replace_cart=False),
            order_repository=order_repo,
            order_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            cart_service=AsyncMock(),
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
        )


@pytest.mark.asyncio
async def test_repeat_order_empty_items_error(base_user, base_order):
    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = base_order

    order_item_repo = AsyncMock()
    order_item_repo.get_by_order_id.return_value = []

    service = OrderService()

    with pytest.raises(OrderItemsNotFoundError):
        await service.repeat_order(
            session=AsyncMock(),
            redis_service=AsyncMock(),
            user=base_user,
            order_id=10,
            data=RepeatOrderRequest(replace_cart=False),
            order_repository=order_repo,
            order_item_repository=order_item_repo,
            product_repository=AsyncMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            cart_service=AsyncMock(),
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
        )


@pytest.mark.asyncio
async def test_repeat_order_replace_cart_clears_existing(base_user, base_order):
    session = AsyncMock()
    redis_service = AsyncMock()

    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = base_order

    order_item = SimpleNamespace(
        id=1,
        order_id=10,
        product_id=100,
        product_name="Молоко",
        quantity=Decimal("2"),
        price=Decimal("80.00"),
    )
    order_item_repo = AsyncMock()
    order_item_repo.get_by_order_id.return_value = [order_item]

    product = SimpleNamespace(
        id=100,
        name="Молоко",
        price=Decimal("80.00"),
        stock_quantity=Decimal("10"),
        is_active=True,
        is_deleted=False,
        is_available=True,
        quantity_step=Decimal("1"),
        product_type="piece",
    )
    product_repo = AsyncMock()
    product_repo.get_by_ids.return_value = [product]

    cart = SimpleNamespace(id=5, user_id=1, promo_code_id=None)
    cart_repo = AsyncMock()
    cart_item_repo = AsyncMock()
    cart_item_repo.get_by_cart_id.return_value = []

    cart_service = AsyncMock()
    cart_service.get_or_create_cart.return_value = cart
    cart_service.recalculate_current_cart.return_value = make_fake_cart_response()

    cart_cache = AsyncMock()
    cart_calc = MagicMock()
    cart_calc.calculate.return_value = SimpleNamespace(
        items=[],
        subtotal=Decimal("160.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
        final_price=Decimal("160.00"),
        items_count=2,
    )

    service = OrderService()
    response = await service.repeat_order(
        session=session,
        redis_service=redis_service,
        user=base_user,
        order_id=10,
        data=RepeatOrderRequest(replace_cart=True),
        order_repository=order_repo,
        order_item_repository=order_item_repo,
        product_repository=product_repo,
        cart_repository=cart_repo,
        cart_item_repository=cart_item_repo,
        promo_code_repository=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=cart_cache,
        cart_calculator_service=cart_calc,
    )

    assert cart_service.clear_cart.called
    assert cart_repo.clear_promo_code.called
    assert response.message == "Товары из заказа добавлены в корзину"
    assert len(response.warnings) == 0


@pytest.mark.asyncio
async def test_repeat_order_with_unavailable_product_warning(base_user, base_order):
    session = AsyncMock()
    redis_service = AsyncMock()

    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = base_order

    order_item_1 = SimpleNamespace(
        id=1,
        order_id=10,
        product_id=200,
        product_name="Сезонные ягоды",
        quantity=Decimal("1"),
        price=Decimal("300.00"),
    )
    order_item_2 = SimpleNamespace(
        id=2,
        order_id=10,
        product_id=201,
        product_name="Хлеб",
        quantity=Decimal("1"),
        price=Decimal("40.00"),
    )
    order_item_repo = AsyncMock()
    order_item_repo.get_by_order_id.return_value = [order_item_1, order_item_2]

    # Товар 1 снят с продажи (is_active=False)
    inactive_product = SimpleNamespace(
        id=200,
        name="Сезонные ягоды",
        price=Decimal("300.00"),
        stock_quantity=Decimal("0"),
        is_active=False,
        is_deleted=False,
        is_available=False,
        quantity_step=Decimal("1"),
        product_type="piece",
    )
    # Товар 2 доступен
    active_product = SimpleNamespace(
        id=201,
        name="Хлеб",
        price=Decimal("40.00"),
        stock_quantity=Decimal("20"),
        is_active=True,
        is_deleted=False,
        is_available=True,
        quantity_step=Decimal("1"),
        product_type="piece",
    )
    product_repo = AsyncMock()
    product_repo.get_by_ids.return_value = [inactive_product, active_product]

    cart = SimpleNamespace(id=5, user_id=1, promo_code_id=None)
    cart_repo = AsyncMock()
    cart_item_repo = AsyncMock()
    cart_item_repo.get_by_cart_id.return_value = []

    cart_service = AsyncMock()
    cart_service.get_or_create_cart.return_value = cart
    cart_service.recalculate_current_cart.return_value = make_fake_cart_response()

    cart_calc = MagicMock()
    cart_calc.calculate.return_value = SimpleNamespace(
        items=[],
        subtotal=Decimal("40.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
        final_price=Decimal("40.00"),
        items_count=1,
    )

    service = OrderService()
    response = await service.repeat_order(
        session=session,
        redis_service=redis_service,
        user=base_user,
        order_id=10,
        data=RepeatOrderRequest(replace_cart=False),
        order_repository=order_repo,
        order_item_repository=order_item_repo,
        product_repository=product_repo,
        cart_repository=cart_repo,
        cart_item_repository=cart_item_repo,
        promo_code_repository=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=cart_calc,
    )

    assert response.message == "Товары из заказа добавлены в корзину"
    assert len(response.warnings) == 1
    assert response.warnings[0].reason == "Товар сейчас недоступен"
    assert response.warnings[0].product_id == 200


@pytest.mark.asyncio
async def test_repeat_order_all_unavailable_raises_error(base_user, base_order):
    from source.errors.auth import RepeatOrderUnavailableError

    session = AsyncMock()
    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = base_order

    order_item = SimpleNamespace(
        id=1,
        order_id=10,
        product_id=300,
        product_name="Товар закончился",
        quantity=Decimal("1"),
        price=Decimal("100.00"),
    )
    order_item_repo = AsyncMock()
    order_item_repo.get_by_order_id.return_value = [order_item]

    out_of_stock_product = SimpleNamespace(
        id=300,
        name="Товар закончился",
        price=Decimal("100.00"),
        stock_quantity=Decimal("0"),
        is_active=True,
        is_deleted=False,
        is_available=True,
        quantity_step=Decimal("1"),
        product_type="piece",
    )
    product_repo = AsyncMock()
    product_repo.get_by_ids.return_value = [out_of_stock_product]

    cart = SimpleNamespace(id=5, user_id=1, promo_code_id=None)
    cart_service = AsyncMock()
    cart_service.get_or_create_cart.return_value = cart
    cart_service.recalculate_current_cart.return_value = make_fake_cart_response()
    cart_item_repo = AsyncMock()
    cart_item_repo.get_by_cart_id.return_value = []

    service = OrderService()
    with pytest.raises(RepeatOrderUnavailableError):
        await service.repeat_order(
            session=session,
            redis_service=AsyncMock(),
            user=base_user,
            order_id=10,
            data=RepeatOrderRequest(replace_cart=False),
            order_repository=order_repo,
            order_item_repository=order_item_repo,
            product_repository=product_repo,
            cart_repository=AsyncMock(),
            cart_item_repository=cart_item_repo,
            promo_code_repository=AsyncMock(),
            cart_service=cart_service,
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
        )
