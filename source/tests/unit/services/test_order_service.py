from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import resolve_access_token
from source.errors.auth import (
    CartEmptyError,
    OrderAccessDeniedError,
    OrderAddressAccessDeniedError,
    OrderNotFoundError,
    OrderAlreadyCancelledError,
    OrderCancellationNotAllowedError,
    OrderPickupPointInactiveError,
    OrderPromoCodeInvalidError,
    OrderUnavailableItemsError,
)
from source.schemas.pydantic.order import OrderCancelRequest, OrderCreateRequest
from source.schemas.pydantic.order import OrderDetailResponse, OrderMyListQueryParams, OrderMyListResponse, OrderShortResponse
from source.services.cart import CartCalculatorService
from source.services.delivery import DeliveryService
from source.services.one_c import OneCIntegrationService
from source.services.order import OrderService
from source.services.order_cache import OrderCacheService
from source.utils.query_hash import build_query_hash
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

    async def release_stock(self, *, session, products_by_id: dict, order_items: list):
        products = []
        for item in order_items:
            product = products_by_id[item.product_id]
            product.stock_quantity += item.quantity
            products.append(product)
        return products


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
        self.cancelled = False

    async def count_by_code(self, *, session, promo_code_id: int) -> int:
        return 0

    async def count_by_user_and_code(self, *, session, user_id: int, promo_code_id: int) -> int:
        return 0

    async def create(self, *, session, promo_code_id: int, user_id: int, order_id: int | None = None, status: str):
        self.created = True
        return SimpleNamespace(id=1, promo_code_id=promo_code_id, user_id=user_id, order_id=order_id, status=status)

    async def cancel_by_order_id(self, *, session, order_id: int) -> None:
        self.cancelled = True


class FakeOrderRepository:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.order = None
        self.fail_create = fail_create

    async def create(self, *, session, **data):
        if self.fail_create:
            raise RuntimeError("boom")
        self.order = SimpleNamespace(id=101, created_date=datetime(2026, 5, 18), **data)
        return self.order


class FakeOrderDetailRepository:
    def __init__(self, order=None) -> None:
        self.order = order
        self.requested_order_id = None

    async def get_by_id(self, *, session, order_id: int):
        self.requested_order_id = order_id
        return self.order if self.order is not None and self.order.id == order_id else None

    async def update_status(self, *, session, order, status: str):
        order.status = status
        return order


class FakeMyOrderRepository:
    def __init__(self, orders=None) -> None:
        self.orders = orders if orders is not None else [
            build_short_order(order_id=101, user_id=1, created_at=datetime(2026, 5, 18)),
            build_short_order(order_id=102, user_id=1, status="completed", payment_status="paid", delivery_type="pickup", created_at=datetime(2026, 5, 17)),
            build_short_order(order_id=103, user_id=2, created_at=datetime(2026, 5, 19)),
        ]
        self.requested_user_id = None

    async def get_by_user_id(self, *, session, user_id: int, query: OrderMyListQueryParams):
        self.requested_user_id = user_id
        orders = self._filter(user_id=user_id, query=query)
        orders.sort(key=lambda order: order.created_at, reverse=True)
        return orders[query.offset : query.offset + query.limit]

    async def count_by_user_id(self, *, session, user_id: int, query: OrderMyListQueryParams | None = None):
        return len(self._filter(user_id=user_id, query=query))

    def _filter(self, *, user_id: int, query: OrderMyListQueryParams | None):
        orders = [order for order in self.orders if order.user_id == user_id]
        if query is None:
            return orders
        if query.status is not None:
            orders = [order for order in orders if order.status == query.status]
        if query.payment_status is not None:
            orders = [order for order in orders if order.payment_status == query.payment_status]
        if query.delivery_type is not None:
            orders = [order for order in orders if order.delivery_type == query.delivery_type]
        if query.date_from is not None:
            orders = [order for order in orders if order.created_at.date() >= query.date_from]
        if query.date_to is not None:
            orders = [order for order in orders if order.created_at.date() <= query.date_to]
        return orders


class FakeOrderItemRepository:
    def __init__(self) -> None:
        self.items = []

    async def bulk_create(self, *, session, items: list[dict]):
        self.items = items
        return items


class FakeOrderDetailItemRepository:
    def __init__(self, items=None) -> None:
        self.items = items if items is not None else [build_order_item()]

    async def get_by_order_id(self, *, session, order_id: int):
        return self.items


class FakePaymentRepository:
    def __init__(self) -> None:
        self.created = False

    async def create(self, **kwargs):
        self.created = True
        return SimpleNamespace(**kwargs)


class FakeOrderDetailPaymentRepository:
    def __init__(self, payment=None) -> None:
        self.payment = payment

    async def get_by_order_id(self, *, session, order_id: int):
        return self.payment


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

    async def invalidate_summary(self, *, redis_service, user_id: int) -> None:
        self.summary_invalidated = True


class FakeOrderCacheService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.invalidated = False

    async def get_my_orders(self, *, redis_service, user_id: int, query_hash: str):
        value = self.values.get(f"orders:my:{user_id}:{query_hash}")
        return None if value is None else OrderMyListResponse.model_validate_json(value)

    async def set_my_orders(self, *, redis_service, user_id: int, query_hash: str, response, ttl_seconds: int):
        key = f"orders:my:{user_id}:{query_hash}"
        self.values[key] = response.model_dump_json()
        self.ttls[key] = ttl_seconds

    async def invalidate_my_orders(self, *, redis_service, user_id: int) -> None:
        self.invalidated = True

    async def get_detail(self, *, redis_service, user_id: int, order_id: int):
        value = self.values.get(f"orders:detail:{user_id}:{order_id}")
        return None if value is None else OrderDetailResponse.model_validate_json(value)

    async def set_detail(self, *, redis_service, user_id: int, order_id: int, response, ttl_seconds: int):
        key = f"orders:detail:{user_id}:{order_id}"
        self.values[key] = response.model_dump_json()
        self.ttls[key] = ttl_seconds

    async def invalidate_detail(self, *, redis_service, user_id: int, order_id: int | None = None) -> None:
        self.invalidated = True

    async def invalidate_order(self, *, redis_service, user_id: int, order_id: int) -> None:
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

    async def notify_order_cancelled(self, **kwargs) -> None:
        self.cancel_notified = True


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


def build_short_order(
    *,
    order_id: int,
    user_id: int,
    status: str = "assembling",
    payment_status: str = "unpaid",
    delivery_type: str = "delivery",
    created_at: datetime,
):
    order = OrderShortResponse(
        id=order_id,
        order_number=f"ORD-{order_id:06d}",
        status=status,
        payment_method="online",
        payment_status=payment_status,
        delivery_type=delivery_type,
        items_count=2,
        final_price=Decimal("100.00"),
        created_at=created_at,
    )
    object.__setattr__(order, "user_id", user_id)
    return order


def build_order_detail(*, user_id: int = 1):
    return SimpleNamespace(
        id=101,
        user_id=user_id,
        order_number="ORD-000101",
        status="assembling",
        payment_method="online",
        payment_status="paid",
        delivery_type="delivery",
        address_id=5,
        pickup_point_id=None,
        customer_name="Иван Иванов",
        customer_phone="+79990000000",
        customer_email="ivan@example.com",
        subtotal=Decimal("270.00"),
        discount_amount=Decimal("45.00"),
        promo_discount_amount=Decimal("100.00"),
        delivery_price=Decimal("250.00"),
        final_price=Decimal("375.00"),
        comment="Позвонить за 10 минут",
        created_date=datetime(2026, 5, 12, 10, 0, 0),
        updated_date=datetime(2026, 5, 12, 11, 0, 0),
        external_1c_id="secret",
        sync_error="secret",
        internal_comment="secret",
        manager_id=7,
        sync_status="sent",
    )


def build_order_item():
    return SimpleNamespace(
        id=1,
        product_id=55,
        product_name="Яблоки красные",
        product_slug="yabloki-krasnye",
        quantity=Decimal("1.5"),
        unit="kg",
        product_type="weight",
        price=Decimal("150.00"),
        old_price=Decimal("180.00"),
        discount_amount=Decimal("45.00"),
        total_price=Decimal("270.00"),
        final_price=Decimal("225.00"),
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
    order_cache_service = FakeOrderCacheService()
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
        order_cache_service=order_cache_service,
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
        order_cache_service=order_cache_service,
        profile_cache_service=profile_cache_service,
        product_cache_service=product_cache_service,
        notification_service=notification_service,
        promo_code_usage_repository=promo_code_usage_repository,
    )


async def execute_get_my_orders(*, order_repository=None, order_cache_service=None, query=None):
    return await OrderService().get_my_orders(
        session=None,
        redis_service=FakeRedisService(),
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        query=query or OrderMyListQueryParams(),
        order_repository=order_repository or FakeMyOrderRepository(),
        order_cache_service=order_cache_service or FakeOrderCacheService(),
    )


async def execute_get_order_detail(
    *,
    order=None,
    order_cache_service=None,
    order_repository=None,
):
    return await OrderService().get_order_detail(
        session=None,
        redis_service=FakeRedisService(),
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        order_id=101,
        order_repository=order_repository or FakeOrderDetailRepository(order or build_order_detail()),
        order_item_repository=FakeOrderDetailItemRepository(),
        address_repository=FakeAddressRepository(
            SimpleNamespace(
                id=5,
                city="Москва",
                street="Тверская",
                house="10",
                apartment="15",
                comment="Позвонить за 10 минут",
            ),
        ),
        pickup_point_repository=FakePickupPointRepository(None),
        payment_repository=FakeOrderDetailPaymentRepository(
            SimpleNamespace(id=9, amount=Decimal("375.00"), status="paid", payment_url=None),
        ),
        order_cache_service=order_cache_service or FakeOrderCacheService(),
    )


async def execute_cancel_order(
    *,
    order="default",
    fail_update=False,
    payment=None,
):
    order = build_order_detail() if order == "default" else order
    if order is not None and payment is None:
        order.payment_status = "unpaid"
    product = build_product(stock_quantity=Decimal("8"))
    promo_usage_repository = FakePromoCodeUsageRepository()
    commiter = FakeCommiter()
    order_repository = FakeOrderDetailRepository(order)
    if fail_update:
        async def broken_update_status(*, session, order, status: str):
            raise RuntimeError("boom")
        order_repository.update_status = broken_update_status
    order_cache_service = FakeOrderCacheService()
    profile_cache_service = FakeProfileCacheService()
    product_cache_service = FakeProductCacheService()
    cart_cache_service = FakeCartCacheService()
    notification_service = FakeNotificationService()
    response = await OrderService().cancel_order(
        session=None,
        commiter=commiter,
        redis_service=FakeRedisService(),
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        order_id=101,
        data=OrderCancelRequest(reason=" Передумал "),
        order_repository=order_repository,
        order_item_repository=FakeOrderDetailItemRepository(),
        product_repository=FakeProductRepository([product]),
        promo_code_usage_repository=promo_usage_repository,
        payment_repository=FakeOrderDetailPaymentRepository(payment),
        stock_service=StockService(),
        promo_code_service=PromoCodeService(),
        payment_service=PaymentService(),
        order_cache_service=order_cache_service,
        profile_cache_service=profile_cache_service,
        product_cache_service=product_cache_service,
        cart_cache_service=cart_cache_service,
        one_c_integration_service=OneCIntegrationService(),
        notification_service=notification_service,
        email_service=FakeEmailService(),
        telegram_service=FakeTelegramService(),
    )
    return SimpleNamespace(
        response=response,
        order=order,
        product=product,
        promo_usage_repository=promo_usage_repository,
        commiter=commiter,
        order_cache_service=order_cache_service,
        profile_cache_service=profile_cache_service,
        product_cache_service=product_cache_service,
        cart_cache_service=cart_cache_service,
        notification_service=notification_service,
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
    assert result.order_cache_service.invalidated is True


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
            order_cache_service=FakeOrderCacheService(),
            profile_cache_service=FakeProfileCacheService(),
            product_cache_service=FakeProductCacheService(),
            one_c_integration_service=OneCIntegrationService(),
            notification_service=FakeNotificationService(),
            email_service=FakeEmailService(),
            telegram_service=FakeTelegramService(),
        )
    assert commiter.rolled_back is True


@pytest.mark.asyncio
async def test_get_my_orders_success() -> None:
    response = await execute_get_my_orders()
    assert response.total == 2
    assert response.page == 1
    assert response.limit == 20
    assert response.pages == 1
    assert [order.id for order in response.items] == [101, 102]


@pytest.mark.asyncio
async def test_get_my_orders_from_redis_cache_success() -> None:
    cache = FakeOrderCacheService()
    query = OrderMyListQueryParams()
    cached_response = OrderMyListResponse(
        items=[build_short_order(order_id=201, user_id=1, created_at=datetime(2026, 5, 18))],
        total=1,
        page=1,
        limit=20,
        pages=1,
    )
    cache.values[f"orders:my:1:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()
    repository = FakeMyOrderRepository()
    response = await execute_get_my_orders(order_repository=repository, order_cache_service=cache, query=query)
    assert [order.id for order in response.items] == [201]
    assert repository.requested_user_id is None


@pytest.mark.asyncio
async def test_get_my_orders_current_user_only() -> None:
    repository = FakeMyOrderRepository()
    response = await execute_get_my_orders(order_repository=repository)
    assert repository.requested_user_id == 1
    assert [order.id for order in response.items] == [101, 102]


@pytest.mark.asyncio
async def test_get_my_orders_filters() -> None:
    response = await execute_get_my_orders(query=OrderMyListQueryParams(status="completed"))
    assert [order.id for order in response.items] == [102]
    response = await execute_get_my_orders(query=OrderMyListQueryParams(payment_status="paid"))
    assert [order.id for order in response.items] == [102]
    response = await execute_get_my_orders(query=OrderMyListQueryParams(delivery_type="pickup"))
    assert [order.id for order in response.items] == [102]


@pytest.mark.asyncio
async def test_get_my_orders_date_filter_pagination_and_sorting() -> None:
    response = await execute_get_my_orders(
        query=OrderMyListQueryParams(
            date_from=datetime(2026, 5, 17).date(),
            date_to=datetime(2026, 5, 18).date(),
            page=2,
            limit=1,
        ),
    )
    assert response.total == 2
    assert response.pages == 2
    assert [order.id for order in response.items] == [102]


@pytest.mark.asyncio
async def test_get_my_orders_response_is_cached() -> None:
    cache = FakeOrderCacheService()
    query = OrderMyListQueryParams(status="assembling")
    await execute_get_my_orders(order_cache_service=cache, query=query)
    key = f"orders:my:1:{build_query_hash(query.model_dump())}"
    assert key in cache.values
    assert cache.ttls[key] == 60


@pytest.mark.asyncio
async def test_get_my_orders_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())
    assert exc_info.value.status_code == 401


def test_get_my_orders_invalid_query_params() -> None:
    with pytest.raises(ValidationError):
        OrderMyListQueryParams(delivery_type="courier")


@pytest.mark.asyncio
async def test_get_order_detail_success() -> None:
    response = await execute_get_order_detail()
    assert response.id == 101
    assert response.address is not None
    assert response.address.city == "Москва"
    assert response.payment is not None
    assert response.payment.status == "paid"


@pytest.mark.asyncio
async def test_get_order_detail_from_cache_success() -> None:
    cache = FakeOrderCacheService()
    cached = await execute_get_order_detail()
    cache.values["orders:detail:1:101"] = cached.model_dump_json()
    repository = FakeOrderDetailRepository(None)
    response = await execute_get_order_detail(order_cache_service=cache, order_repository=repository)
    assert response.id == 101
    assert repository.requested_order_id is None


@pytest.mark.asyncio
async def test_get_order_detail_access_denied() -> None:
    with pytest.raises(OrderAccessDeniedError):
        await execute_get_order_detail(order=build_order_detail(user_id=2))


@pytest.mark.asyncio
async def test_get_order_detail_not_found() -> None:
    with pytest.raises(OrderNotFoundError):
        await execute_get_order_detail(order_repository=FakeOrderDetailRepository(None))


@pytest.mark.asyncio
async def test_get_order_detail_items_are_snapshot_and_service_fields_hidden() -> None:
    response = await execute_get_order_detail()
    assert response.items[0].product_name == "Яблоки красные"
    assert response.items[0].price == Decimal("150.00")
    dumped = response.model_dump()
    assert "external_1c_id" not in dumped
    assert "sync_error" not in dumped
    assert "internal_comment" not in dumped
    assert "manager_id" not in dumped


@pytest.mark.asyncio
async def test_get_order_detail_response_is_cached() -> None:
    cache = FakeOrderCacheService()
    await execute_get_order_detail(order_cache_service=cache)
    assert "orders:detail:1:101" in cache.values
    assert cache.ttls["orders:detail:1:101"] == 60


@pytest.mark.asyncio
async def test_cancel_order_new_success() -> None:
    order = build_order_detail()
    order.status = "new"
    result = await execute_cancel_order(order=order)
    assert result.response.message == "Заказ отменён"
    assert result.response.order.status == "cancelled"
    assert result.response.order.cancel_reason == "Передумал"


@pytest.mark.asyncio
async def test_cancel_order_pending_payment_success() -> None:
    order = build_order_detail()
    order.status = "pending_payment"
    result = await execute_cancel_order(order=order)
    assert result.response.order.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_order_access_denied() -> None:
    order = build_order_detail(user_id=2)
    with pytest.raises(OrderAccessDeniedError):
        await execute_cancel_order(order=order)


@pytest.mark.asyncio
async def test_cancel_order_not_found() -> None:
    with pytest.raises(OrderNotFoundError):
        await execute_cancel_order(order=None)


@pytest.mark.asyncio
async def test_cancel_order_already_cancelled_error() -> None:
    order = build_order_detail()
    order.status = "cancelled"
    with pytest.raises(OrderAlreadyCancelledError):
        await execute_cancel_order(order=order)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["assembling", "delivering"])
async def test_cancel_order_disallowed_status_error(status: str) -> None:
    order = build_order_detail()
    order.status = status
    with pytest.raises(OrderCancellationNotAllowedError):
        await execute_cancel_order(order=order)


@pytest.mark.asyncio
async def test_cancel_order_releases_stock_and_cancels_promo_usage() -> None:
    order = build_order_detail()
    order.status = "new"
    result = await execute_cancel_order(order=order)
    assert result.product.stock_quantity == Decimal("9.5")
    assert result.promo_usage_repository.cancelled is True


@pytest.mark.asyncio
async def test_cancel_order_marks_pending_cancel_for_synced_order() -> None:
    order = build_order_detail()
    order.status = "new"
    order.sync_status = "sent"
    result = await execute_cancel_order(order=order)
    assert result.order.sync_status == "pending_cancel"


@pytest.mark.asyncio
async def test_cancel_order_invalidates_cache() -> None:
    order = build_order_detail()
    order.status = "new"
    result = await execute_cancel_order(order=order)
    assert result.order_cache_service.invalidated is True
    assert result.profile_cache_service.orders_invalidated is True
    assert result.profile_cache_service.summary_deleted is True
    assert result.product_cache_service.invalidated is True
    assert result.cart_cache_service.summary_invalidated is True


@pytest.mark.asyncio
async def test_cancel_order_rolls_back_on_error() -> None:
    order = build_order_detail()
    order.status = "new"
    with pytest.raises(RuntimeError):
        await execute_cancel_order(order=order, fail_update=True)
