from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.errors.auth import (
    CartEmptyError,
    OrderAddressAccessDeniedError,
    OrderPickupPointInactiveError,
    OrderPromoCodeInvalidError,
    OrderUnavailableItemsError,
)
from source.schemas.pydantic.order import OrderCreateRequest
from source.services.cart import CartCalculatorService
from source.services.delivery import DeliveryService
from source.services.one_c import OneCIntegrationService
from source.services.order import OrderService
from source.services.payment import PaymentService
from source.services.promo_code import PromoCodeService
from source.services.stock import StockService


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeCartRepository:
    def __init__(self, cart) -> None:
        self.cart = cart

    async def get_by_user_id(self, *, session, user_id: int):
        return self.cart if self.cart and self.cart.user_id == user_id else None

    async def clear_promo_code(self, *, session, cart):
        cart.promo_code_id = None
        return cart


class FakeCartItemRepository:
    def __init__(self, items) -> None:
        self.items = items
        self.cleared = False

    async def get_by_cart_id(self, *, session, cart_id: int):
        return self.items

    async def delete_by_cart_id(self, *, session, cart_id: int) -> None:
        self.items = []
        self.cleared = True


class FakeProductRepository:
    def __init__(self, products) -> None:
        self.products = products

    async def get_by_ids(self, *, session, product_ids: list[int]):
        return [product for product in self.products if product.id in product_ids]


class FakeAddressRepository:
    def __init__(self, address) -> None:
        self.address = address

    async def get_by_id(self, *, session, address_id: int):
        return self.address if self.address and self.address.id == address_id else None


class FakePickupPointRepository:
    def __init__(self, pickup_point) -> None:
        self.pickup_point = pickup_point

    async def get_by_id(self, *, session, pickup_point_id: int):
        return self.pickup_point if self.pickup_point and self.pickup_point.id == pickup_point_id else None


class FakePromoCodeRepository:
    def __init__(self, promo_code=None) -> None:
        self.promo_code = promo_code

    async def get_by_id(self, *, session, promo_code_id: int):
        return self.promo_code if self.promo_code and self.promo_code.id == promo_code_id else None


class FakePromoCodeUsageRepository:
    def __init__(self) -> None:
        self.created = False

    async def count_by_code(self, *, session, promo_code_id: int) -> int:
        return 0

    async def count_by_user_and_code(self, *, session, user_id: int, promo_code_id: int) -> int:
        return 0

    async def create(self, *, session, promo_code_id: int, user_id: int, status: str):
        self.created = True
        return SimpleNamespace(id=1, promo_code_id=promo_code_id, user_id=user_id, status=status)


class FakeOrderRepository:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.order = None
        self.fail_create = fail_create

    async def create(self, *, session, **data):
        if self.fail_create:
            raise RuntimeError("boom")
        self.order = SimpleNamespace(id=101, created_date=datetime(2026, 5, 18), **data)
        return self.order


class FakeOrderItemRepository:
    def __init__(self) -> None:
        self.items = []

    async def bulk_create(self, *, session, items: list[dict]):
        self.items = items
        return items


class FakePaymentRepository:
    def __init__(self) -> None:
        self.created = False

    async def create(self, **kwargs):
        self.created = True
        return SimpleNamespace(**kwargs)


class FakeRedisService:
    def __init__(self) -> None:
        self.deleted = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted.append(pattern)


class FakeCartCacheService:
    def __init__(self) -> None:
        self.invalidated = False

    async def invalidate_cart(self, *, redis_service, user_id: int) -> None:
        self.invalidated = True


class FakeProfileCacheService:
    def __init__(self) -> None:
        self.orders_invalidated = False
        self.summary_deleted = False

    async def invalidate_orders(self, *, redis_service, user_id: int) -> None:
        self.orders_invalidated = True

    async def delete_summary(self, *, redis_service, user_id: int) -> None:
        self.summary_deleted = True


class FakeProductCacheService:
    def __init__(self) -> None:
        self.invalidated = False

    async def invalidate_by_stock_changes(self, *, redis_service, products: list) -> None:
        self.invalidated = True


class FakeNotificationService:
    def __init__(self) -> None:
        self.notified = False

    async def notify_order_created(self, **kwargs) -> None:
        self.notified = True


class FakeEmailService:
    pass


class FakeTelegramService:
    pass


def build_product(*, stock_quantity=Decimal("10"), is_active=True, is_available=True):
    return SimpleNamespace(
        id=55,
        name="Яблоки красные",
        slug="yabloki-krasnye",
        preview_image_url="/media/products/yabloki-krasnye.png",
        unit="kg",
        product_type="weight",
        price=Decimal("150.00"),
        old_price=Decimal("180.00"),
        stock_quantity=stock_quantity,
        is_active=is_active,
        is_deleted=False,
        is_available=is_available,
        category_id=1,
    )


def build_cart_item(quantity=Decimal("2")):
    return SimpleNamespace(
        id=1,
        cart_id=10,
        product_id=55,
        name="Старое название",
        quantity=quantity,
        unit="kg",
        price=Decimal("999.00"),
    )


def build_promo_code(*, is_active=True):
    return SimpleNamespace(
        id=7,
        code="PROMO10",
        discount_type="percent",
        discount_value=Decimal("10"),
        min_order_amount=None,
        usage_limit=None,
        per_user_usage_limit=None,
        applicable_category_id=None,
        applicable_product_id=None,
        allow_discounted_products=True,
        is_active=is_active,
        starts_at=None,
        ends_at=None,
    )


async def execute_create_order(
    *,
    delivery_type="delivery",
    payment_method="on_delivery",
    items=None,
    product=None,
    cart=None,
    address=None,
    pickup_point=None,
    promo_code=None,
    fail_create=False,
):
    items = [build_cart_item()] if items is None else items
    product = build_product() if product is None else product
    cart = SimpleNamespace(id=10, user_id=1, promo_code_id=None if promo_code is None else promo_code.id) if cart is None else cart
    address = SimpleNamespace(id=5, user_id=1, is_deleted=False) if address is None else address
    pickup_point = SimpleNamespace(id=1, is_active=True) if pickup_point is None else pickup_point
    commiter = FakeCommiter()
    cart_item_repository = FakeCartItemRepository(items)
    order_repository = FakeOrderRepository(fail_create=fail_create)
    order_item_repository = FakeOrderItemRepository()
    payment_repository = FakePaymentRepository()
    cart_cache_service = FakeCartCacheService()
    profile_cache_service = FakeProfileCacheService()
    product_cache_service = FakeProductCacheService()
    notification_service = FakeNotificationService()
    promo_code_usage_repository = FakePromoCodeUsageRepository()
    response = await OrderService().create_order(
        session=None,
        commiter=commiter,
        redis_service=FakeRedisService(),
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        data=OrderCreateRequest(
            delivery_type=delivery_type,
            payment_method=payment_method,
            address_id=5 if delivery_type == "delivery" else None,
            pickup_point_id=1 if delivery_type == "pickup" else None,
            customer_name="Иван Иванов",
            customer_phone="+79990000000",
            customer_email="ivan@example.com",
        ),
        cart_repository=FakeCartRepository(cart),
        cart_item_repository=cart_item_repository,
        product_repository=FakeProductRepository([product]),
        address_repository=FakeAddressRepository(address),
        pickup_point_repository=FakePickupPointRepository(pickup_point),
        promo_code_repository=FakePromoCodeRepository(promo_code),
        promo_code_usage_repository=promo_code_usage_repository,
        order_repository=order_repository,
        order_item_repository=order_item_repository,
        payment_repository=payment_repository,
        cart_calculator_service=CartCalculatorService(),
        stock_service=StockService(),
        promo_code_service=PromoCodeService(),
        delivery_service=DeliveryService(),
        payment_service=PaymentService(),
        cart_cache_service=cart_cache_service,
        profile_cache_service=profile_cache_service,
        product_cache_service=product_cache_service,
        one_c_integration_service=OneCIntegrationService(),
        notification_service=notification_service,
        email_service=FakeEmailService(),
        telegram_service=FakeTelegramService(),
    )
    return SimpleNamespace(
        response=response,
        product=product,
        commiter=commiter,
        cart_item_repository=cart_item_repository,
        order_repository=order_repository,
        order_item_repository=order_item_repository,
        payment_repository=payment_repository,
        cart_cache_service=cart_cache_service,
        profile_cache_service=profile_cache_service,
        product_cache_service=product_cache_service,
        notification_service=notification_service,
        promo_code_usage_repository=promo_code_usage_repository,
    )


@pytest.mark.asyncio
async def test_create_order_delivery_success() -> None:
    result = await execute_create_order()
    assert result.response.delivery_type == "delivery"
    assert result.response.delivery_price == Decimal("250.00")


@pytest.mark.asyncio
async def test_create_order_pickup_success() -> None:
    result = await execute_create_order(delivery_type="pickup")
    assert result.response.delivery_type == "pickup"
    assert result.response.delivery_price == Decimal("0")


@pytest.mark.asyncio
async def test_create_order_online_payment_success() -> None:
    result = await execute_create_order(payment_method="online")
    assert result.response.status == "pending_payment"
    assert result.response.payment_url == "https://payment.example.com/pay/101"
    assert result.payment_repository.created is True


@pytest.mark.asyncio
async def test_create_order_on_delivery_success() -> None:
    result = await execute_create_order(payment_method="on_delivery")
    assert result.response.status == "new"
    assert result.response.payment_url is None


@pytest.mark.asyncio
async def test_create_order_empty_cart_error() -> None:
    with pytest.raises(CartEmptyError):
        await execute_create_order(items=[])


@pytest.mark.asyncio
async def test_create_order_unavailable_product_error() -> None:
    with pytest.raises(OrderUnavailableItemsError):
        await execute_create_order(product=build_product(is_available=False))


@pytest.mark.asyncio
async def test_create_order_insufficient_stock_error() -> None:
    with pytest.raises(OrderUnavailableItemsError):
        await execute_create_order(product=build_product(stock_quantity=Decimal("1")))


@pytest.mark.asyncio
async def test_create_order_address_access_denied_error() -> None:
    with pytest.raises(OrderAddressAccessDeniedError):
        await execute_create_order(address=SimpleNamespace(id=5, user_id=2, is_deleted=False))


@pytest.mark.asyncio
async def test_create_order_inactive_pickup_point_error() -> None:
    with pytest.raises(OrderPickupPointInactiveError):
        await execute_create_order(delivery_type="pickup", pickup_point=SimpleNamespace(id=1, is_active=False))


@pytest.mark.asyncio
async def test_create_order_promo_code_applied() -> None:
    result = await execute_create_order(promo_code=build_promo_code())
    assert result.response.promo_discount_amount == Decimal("30.0000")
    assert result.promo_code_usage_repository.created is True


@pytest.mark.asyncio
async def test_create_order_invalid_promo_code_error() -> None:
    with pytest.raises(OrderPromoCodeInvalidError):
        await execute_create_order(promo_code=build_promo_code(is_active=False))


@pytest.mark.asyncio
async def test_create_order_items_snapshot_current_product_values() -> None:
    result = await execute_create_order()
    order_item = result.order_item_repository.items[0]
    assert order_item["product_name"] == "Яблоки красные"
    assert order_item["price"] == Decimal("150.00")


@pytest.mark.asyncio
async def test_create_order_clears_cart_and_invalidates_cache() -> None:
    result = await execute_create_order()
    assert result.cart_item_repository.cleared is True
    assert result.cart_cache_service.invalidated is True
    assert result.profile_cache_service.orders_invalidated is True
    assert result.profile_cache_service.summary_deleted is True
    assert result.product_cache_service.invalidated is True


@pytest.mark.asyncio
async def test_create_order_marks_pending_sync_and_reserves_stock() -> None:
    result = await execute_create_order()
    assert result.order_repository.order.sync_status == "pending"
    assert result.product.stock_quantity == Decimal("8")


@pytest.mark.asyncio
async def test_create_order_rolls_back_on_error() -> None:
    commiter = FakeCommiter()
    with pytest.raises(RuntimeError):
        await OrderService().create_order(
            session=None,
            commiter=commiter,
            redis_service=FakeRedisService(),
            user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
            data=OrderCreateRequest(
                delivery_type="delivery",
                payment_method="on_delivery",
                address_id=5,
                customer_name="Иван Иванов",
                customer_phone="+79990000000",
            ),
            cart_repository=FakeCartRepository(SimpleNamespace(id=10, user_id=1, promo_code_id=None)),
            cart_item_repository=FakeCartItemRepository([build_cart_item()]),
            product_repository=FakeProductRepository([build_product()]),
            address_repository=FakeAddressRepository(SimpleNamespace(id=5, user_id=1, is_deleted=False)),
            pickup_point_repository=FakePickupPointRepository(None),
            promo_code_repository=FakePromoCodeRepository(),
            promo_code_usage_repository=FakePromoCodeUsageRepository(),
            order_repository=FakeOrderRepository(fail_create=True),
            order_item_repository=FakeOrderItemRepository(),
            payment_repository=FakePaymentRepository(),
            cart_calculator_service=CartCalculatorService(),
            stock_service=StockService(),
            promo_code_service=PromoCodeService(),
            delivery_service=DeliveryService(),
            payment_service=PaymentService(),
            cart_cache_service=FakeCartCacheService(),
            profile_cache_service=FakeProfileCacheService(),
            product_cache_service=FakeProductCacheService(),
            one_c_integration_service=OneCIntegrationService(),
            notification_service=FakeNotificationService(),
            email_service=FakeEmailService(),
            telegram_service=FakeTelegramService(),
        )
    assert commiter.rolled_back is True
