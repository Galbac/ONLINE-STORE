from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.db.models.choises.enum import UserRole
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    OrderFieldNotEditableError,
    OrderNotFoundError,
    OrderStatusTransitionError,
    OrderUpdateNotAllowedError,
)
from source.schemas.pydantic.order import (
    AdminOrderListItemResponse,
    AdminOrderListQueryParams,
    AdminOrderListResponse,
    AdminOrderStatusUpdateRequest,
    AdminOrderUpdateRequest,
)
from source.services.admin_auth import PermissionService
from source.services.admin_order import AdminOrderService
from source.services.order_cache import OrderCacheService
from source.services.order_status import OrderStatusService


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted = []
        self.deleted_patterns = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)
        self.values = {key: value for key, value in self.values.items() if not key.startswith(pattern.rstrip("*"))}

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class FakeOrderRepository:
    def __init__(self, orders) -> None:
        self.orders = orders
        self.list_calls = 0
        self.count_calls = 0

    async def admin_get_list(self, *, session, query: AdminOrderListQueryParams):
        self.list_calls += 1
        orders = self._filter(query)
        orders.sort(key=lambda order: order.created_date, reverse=True)
        return [build_item(order) for order in orders[query.offset : query.offset + query.limit]]

    async def admin_count(self, *, session, query: AdminOrderListQueryParams) -> int:
        self.count_calls += 1
        return len(self._filter(query))

    async def admin_get_by_id(self, *, session, order_id: int):
        self.list_calls += 1
        return next((order for order in self.orders if order.id == order_id), None)

    async def update_status(self, *, session, order, status: str, sync_status: str | None = None):
        order.status = status
        if sync_status is not None:
            order.sync_status = sync_status
        order.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return order

    async def update_allowed_fields(self, *, session, order, data: dict):
        for field, value in data.items():
            setattr(order, field, value)
        order.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return order

    def _filter(self, query: AdminOrderListQueryParams):
        orders = list(self.orders)
        if query.q is not None:
            q = query.q.lower()
            orders = [
                order
                for order in orders
                if q in order.order_number.lower()
                or q in order.customer_phone.lower()
                or q in (order.customer_email or "").lower()
                or q in order.customer_name.lower()
            ]
        if query.status is not None:
            orders = [order for order in orders if order.status == query.status]
        if query.payment_status is not None:
            orders = [order for order in orders if order.payment_status == query.payment_status]
        if query.sync_status is not None:
            orders = [order for order in orders if order.sync_status == query.sync_status]
        return orders


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False)


def build_order(
    *,
    order_id: int,
    order_number: str,
    status: str = "new",
    payment_status: str = "unpaid",
    customer_name: str = "Иван Иванов",
    customer_phone: str = "+79990000000",
        customer_email: str | None = "ivan@example.com",
        sync_status: str = "pending",
        created_date: datetime | None = None,
):
    return SimpleNamespace(
        id=order_id,
        order_number=order_number,
        status=status,
        payment_method="online",
        payment_status=payment_status,
        delivery_type="delivery",
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        final_price=Decimal("3250.00"),
        sync_status=sync_status,
        external_1c_id=None,
        created_date=created_date or datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=order_id),
        updated_date=datetime(2026, 5, 12, 10, 30, 0),
        address_id=10,
        pickup_point_id=None,
        delivery_date=None,
        delivery_time_slot_id=None,
        user_id=1,
        subtotal=Decimal("270.00"),
        discount_amount=Decimal("45.00"),
        promo_discount_amount=Decimal("100.00"),
        delivery_price=Decimal("250.00"),
        comment="Позвонить заранее",
        internal_comment=None,
        cancel_reason=None,
    )


def build_item(order) -> AdminOrderListItemResponse:
    return AdminOrderListItemResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        delivery_type=order.delivery_type,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        final_price=order.final_price,
        sync_status=order.sync_status,
        created_at=order.created_date,
    )


async def get_orders(*, orders=None, query=None, redis_service=None, role=UserRole.ADMIN, repository=None):
    repository = repository or FakeOrderRepository(orders or [])
    return await AdminOrderService().get_orders(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        query=query or AdminOrderListQueryParams(),
        permission_service=PermissionService(),
        order_repository=repository,
        order_cache_service=OrderCacheService(),
    )


class FakeOrderItemRepository:
    def __init__(self, items=None) -> None:
        self.items = items or []

    async def get_by_order_id(self, *, session, order_id: int):
        return self.items


class FakeAddressRepository:
    def __init__(self, address=None) -> None:
        self.address = address or SimpleNamespace(city="Москва", street="Тверская", house="10", apartment="15")

    async def get_by_id(self, *, session, address_id: int):
        return self.address


class FakePickupPointRepository:
    async def get_by_id(self, *, session, pickup_point_id: int):
        return SimpleNamespace(id=pickup_point_id, name="ПВЗ", city="Москва", address="Тверская, 10")


class FakePaymentRepository:
    def __init__(self, payment=None) -> None:
        self.payment = payment

    async def get_by_order_id(self, *, session, order_id: int):
        return self.payment


class FakeOrderStatusHistoryRepository:
    def __init__(self, items=None) -> None:
        self.items = items or []

    async def get_by_order_id(self, *, session, order_id: int):
        return self.items

    async def create(self, *, session, **data):
        history = SimpleNamespace(id=len(self.items) + 1, created_date=datetime(2026, 5, 12, 11), **data)
        self.items.append(history)
        return history


def build_order_item():
    return SimpleNamespace(
        id=1,
        product_id=55,
        product_name="Яблоки красные",
        quantity=Decimal("1.5"),
        unit="kg",
        price=Decimal("150.00"),
        final_price=Decimal("225.00"),
    )


def build_payment():
    return SimpleNamespace(
        id=5,
        amount=Decimal("375.00"),
        currency="RUB",
        status="paid",
        provider="yookassa",
        provider_payment_id="pay_1",
        paid_at=datetime(2026, 5, 12, 10, 5, 0),
        cancelled_at=None,
        refund_status=None,
    )


async def get_order_detail(*, orders=None, order_id: int = 101, redis_service=None, role=UserRole.ADMIN, repository=None):
    repository = repository or FakeOrderRepository(orders or [build_order(order_id=order_id, order_number="ORD-000101")])
    return await AdminOrderService().get_order_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        order_id=order_id,
        permission_service=PermissionService(),
        order_repository=repository,
        order_item_repository=FakeOrderItemRepository([build_order_item()]),
        address_repository=FakeAddressRepository(),
        pickup_point_repository=FakePickupPointRepository(),
        payment_repository=FakePaymentRepository(build_payment()),
        order_status_history_repository=FakeOrderStatusHistoryRepository(),
        order_cache_service=OrderCacheService(),
    )


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeNotificationRepository:
    def __init__(self) -> None:
        self.notifications = []

    async def create(self, *, session, **data):
        notification = SimpleNamespace(id=len(self.notifications) + 1, **data)
        self.notifications.append(notification)
        return notification


class FakeNotificationService:
    def __init__(self) -> None:
        self.notified = False

    async def notify_order_status_changed(
        self,
        *,
        session,
        order,
        notification_repository,
        email_service,
        telegram_service,
    ) -> None:
        self.notified = True
        await notification_repository.create(
            session=session,
            user_id=order.user_id,
            type="order_status",
            title="Статус заказа изменён",
            message=order.status,
        )


class FakeProfileCacheService:
    def __init__(self) -> None:
        self.summary_deleted = False
        self.orders_invalidated = False

    async def invalidate_orders(self, *, redis_service, user_id: int) -> None:
        self.orders_invalidated = True
        await redis_service.delete_by_pattern(f"profile:orders:{user_id}:*")

    async def delete_summary(self, *, redis_service, user_id: int) -> None:
        self.summary_deleted = True
        await redis_service.delete(f"profile:summary:{user_id}")


class FakeAdminAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)


async def update_order_status(
    *,
    order=None,
    status: str = "assembling",
    notify_customer: bool = False,
    role=UserRole.ADMIN,
):
    redis_service = FakeRedisService()
    repository = FakeOrderRepository([] if order is None else [order])
    history_repository = FakeOrderStatusHistoryRepository()
    notification_repository = FakeNotificationRepository()
    notification_service = FakeNotificationService()
    profile_cache_service = FakeProfileCacheService()
    commiter = FakeCommiter()

    response = await AdminOrderService().update_status(
        session=None,
        commiter=commiter,
        redis_service=redis_service,
        user=build_user(role=role),
        order_id=101,
        data=AdminOrderStatusUpdateRequest(
            status=status,
            comment="Заказ передан в сборку",
            notify_customer=notify_customer,
        ),
        permission_service=PermissionService(),
        order_repository=repository,
        order_status_history_repository=history_repository,
        order_status_service=OrderStatusService(),
        notification_service=notification_service,
        notification_repository=notification_repository,
        email_service=SimpleNamespace(),
        telegram_service=SimpleNamespace(),
        order_cache_service=OrderCacheService(),
        profile_cache_service=profile_cache_service,
    )
    return SimpleNamespace(
        response=response,
        order=order,
        redis_service=redis_service,
        history_repository=history_repository,
        notification_repository=notification_repository,
        notification_service=notification_service,
        profile_cache_service=profile_cache_service,
        commiter=commiter,
    )


async def update_order(
    *,
    order=None,
    data: AdminOrderUpdateRequest | None = None,
    role=UserRole.ADMIN,
):
    redis_service = FakeRedisService()
    repository = FakeOrderRepository([] if order is None else [order])
    audit_repository = FakeAdminAuditLogRepository()
    profile_cache_service = FakeProfileCacheService()
    commiter = FakeCommiter()

    response = await AdminOrderService().update_order(
        session=None,
        commiter=commiter,
        redis_service=redis_service,
        user=build_user(role=role),
        order_id=101,
        data=data or AdminOrderUpdateRequest(comment="Новый комментарий"),
        permission_service=PermissionService(),
        order_repository=repository,
        admin_audit_log_repository=audit_repository,
        order_cache_service=OrderCacheService(),
        profile_cache_service=profile_cache_service,
    )
    return SimpleNamespace(
        response=response,
        order=order,
        redis_service=redis_service,
        audit_repository=audit_repository,
        profile_cache_service=profile_cache_service,
        commiter=commiter,
    )


@pytest.mark.asyncio
async def test_admin_get_orders_success() -> None:
    response = await get_orders(
        orders=[
            build_order(order_id=1, order_number="ORD-000001"),
            build_order(order_id=2, order_number="ORD-000002"),
        ],
    )

    assert response.total == 2
    assert [item.order_number for item in response.items] == ["ORD-000002", "ORD-000001"]
    assert response.page == 1
    assert response.limit == 50


@pytest.mark.asyncio
async def test_admin_get_orders_filters_by_status() -> None:
    response = await get_orders(
        orders=[
            build_order(order_id=1, order_number="ORD-000001", status="new"),
            build_order(order_id=2, order_number="ORD-000002", status="cancelled"),
        ],
        query=AdminOrderListQueryParams(status="cancelled"),
    )

    assert response.total == 1
    assert response.items[0].status == "cancelled"


@pytest.mark.asyncio
async def test_admin_get_orders_filters_by_payment_status() -> None:
    response = await get_orders(
        orders=[
            build_order(order_id=1, order_number="ORD-000001", payment_status="paid"),
            build_order(order_id=2, order_number="ORD-000002", payment_status="unpaid"),
        ],
        query=AdminOrderListQueryParams(payment_status="paid"),
    )

    assert response.total == 1
    assert response.items[0].payment_status == "paid"


@pytest.mark.asyncio
async def test_admin_get_orders_searches_by_q() -> None:
    response = await get_orders(
        orders=[
            build_order(order_id=1, order_number="ORD-000001", customer_name="Иван Иванов"),
            build_order(order_id=2, order_number="ORD-000002", customer_name="Петр Петров"),
        ],
        query=AdminOrderListQueryParams(q="петр"),
    )

    assert response.total == 1
    assert response.items[0].customer_name == "Петр Петров"


@pytest.mark.asyncio
async def test_admin_get_orders_filters_by_sync_status() -> None:
    response = await get_orders(
        orders=[
            build_order(order_id=1, order_number="ORD-000001", sync_status="pending"),
            build_order(order_id=2, order_number="ORD-000002", sync_status="synced"),
        ],
        query=AdminOrderListQueryParams(sync_status="synced"),
    )

    assert response.total == 1
    assert response.items[0].sync_status == "synced"


@pytest.mark.asyncio
async def test_admin_get_orders_pagination() -> None:
    response = await get_orders(
        orders=[
            build_order(order_id=1, order_number="ORD-000001"),
            build_order(order_id=2, order_number="ORD-000002"),
            build_order(order_id=3, order_number="ORD-000003"),
        ],
        query=AdminOrderListQueryParams(page=2, limit=2),
    )

    assert response.total == 3
    assert response.pages == 2
    assert [item.order_number for item in response.items] == ["ORD-000001"]


@pytest.mark.asyncio
async def test_admin_get_orders_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_orders(
            orders=[build_order(order_id=1, order_number="ORD-000001")],
            role=UserRole.PICKER,
        )


@pytest.mark.asyncio
async def test_admin_get_orders_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminOrderListResponse.build(
        items=[build_item(build_order(order_id=1, order_number="ORD-CACHED"))],
        total=1,
        page=1,
        limit=50,
    )
    await OrderCacheService().set_admin_list(
        redis_service=redis_service,
        query_hash="cached",
        response=cached_response,
        ttl_seconds=60,
    )
    repository = FakeOrderRepository([build_order(order_id=2, order_number="ORD-DB")])

    from source.utils.query_hash import build_query_hash

    query = AdminOrderListQueryParams()
    redis_service.values[f"admin:orders:list:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()

    response = await get_orders(query=query, redis_service=redis_service, repository=repository)

    assert response.items[0].order_number == "ORD-CACHED"
    assert repository.list_calls == 0
    assert repository.count_calls == 0


@pytest.mark.asyncio
async def test_admin_get_order_detail_success() -> None:
    response = await get_order_detail()

    assert response.id == 101
    assert response.order_number == "ORD-000101"
    assert response.customer.name == "Иван Иванов"
    assert response.address.city == "Москва"
    assert response.items[0].product_name == "Яблоки красные"
    assert response.payment.status == "paid"


@pytest.mark.asyncio
async def test_admin_get_order_detail_not_found_error() -> None:
    with pytest.raises(OrderNotFoundError):
        await get_order_detail(orders=[], repository=FakeOrderRepository([]))


@pytest.mark.asyncio
async def test_admin_get_order_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_order_detail(role=UserRole.PICKER)


@pytest.mark.asyncio
async def test_admin_get_order_detail_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = await get_order_detail()
    await OrderCacheService().set_admin_detail(
        redis_service=redis_service,
        order_id=101,
        response=cached_response,
        ttl_seconds=60,
    )
    repository = FakeOrderRepository([build_order(order_id=102, order_number="ORD-DB")])

    response = await get_order_detail(redis_service=redis_service, repository=repository)

    assert response.order_number == "ORD-000101"
    assert repository.list_calls == 0


@pytest.mark.asyncio
async def test_admin_get_order_detail_returns_sync_fields() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", sync_status="pending")
    order.external_1c_id = "1c-101"

    response = await get_order_detail(orders=[order])

    assert response.sync_status == "pending"
    assert response.external_1c_id == "1c-101"


@pytest.mark.asyncio
async def test_admin_update_order_status_success() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order_status(order=order)

    assert result.response.id == 101
    assert result.response.order_number == "ORD-000101"
    assert result.response.status == "assembling"
    assert order.status == "assembling"
    assert order.sync_status == "pending_status_update"
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_update_order_status_invalid_transition() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="completed")

    with pytest.raises(OrderStatusTransitionError):
        await update_order_status(order=order, status="assembling")


@pytest.mark.asyncio
async def test_admin_update_order_status_not_found() -> None:
    with pytest.raises(OrderNotFoundError):
        await update_order_status(order=None)


@pytest.mark.asyncio
async def test_admin_update_order_status_creates_history() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order_status(order=order)

    assert len(result.history_repository.items) == 1
    history = result.history_repository.items[0]
    assert history.order_id == 101
    assert history.old_status == "new"
    assert history.status == "assembling"
    assert history.comment == "Заказ передан в сборку"
    assert history.changed_by == 1


@pytest.mark.asyncio
async def test_admin_update_order_status_creates_notification() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order_status(order=order, notify_customer=True)

    assert result.notification_service.notified is True
    assert len(result.notification_repository.notifications) == 1
    assert result.notification_repository.notifications[0].type == "order_status"


@pytest.mark.asyncio
async def test_admin_update_order_status_invalidates_cache() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order_status(order=order)

    assert "admin:orders:*" in result.redis_service.deleted_patterns
    assert "orders:my:1:*" in result.redis_service.deleted_patterns
    assert "orders:detail:1:101" in result.redis_service.deleted
    assert "orders:status:1:101" in result.redis_service.deleted
    assert "profile:summary:1" in result.redis_service.deleted
    assert result.profile_cache_service.summary_deleted is True


@pytest.mark.asyncio
async def test_admin_update_order_comment_success() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order(order=order, data=AdminOrderUpdateRequest(comment="Новый комментарий"))

    assert result.response.id == 101
    assert result.response.comment == "Новый комментарий"
    assert order.comment == "Новый комментарий"
    assert order.sync_status == "pending_update"
    assert result.commiter.committed is True


def test_admin_update_order_forbids_final_price() -> None:
    with pytest.raises(OrderFieldNotEditableError):
        AdminOrderService().validate_update_payload_fields(payload={"final_price": "100.00"})


@pytest.mark.asyncio
async def test_admin_update_order_not_found() -> None:
    with pytest.raises(OrderNotFoundError):
        await update_order(order=None, data=AdminOrderUpdateRequest(comment="Новый комментарий"))


@pytest.mark.asyncio
async def test_admin_update_order_invalid_status() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="completed")

    with pytest.raises(OrderUpdateNotAllowedError):
        await update_order(order=order, data=AdminOrderUpdateRequest(comment="Новый комментарий"))


@pytest.mark.asyncio
async def test_admin_update_order_creates_audit_log() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order(
        order=order,
        data=AdminOrderUpdateRequest(
            customer_name="Иван Петров",
            internal_comment="Позвонить перед сборкой",
        ),
    )

    assert len(result.audit_repository.logs) == 1
    log = result.audit_repository.logs[0]
    assert log["event"] == "admin_order_update"
    assert log["details"]["order_id"] == 101
    assert log["details"]["diff"]["customer_name"] == {
        "old": "Иван Иванов",
        "new": "Иван Петров",
    }
    assert log["details"]["diff"]["internal_comment"] == {
        "old": None,
        "new": "Позвонить перед сборкой",
    }


@pytest.mark.asyncio
async def test_admin_update_order_invalidates_cache() -> None:
    order = build_order(order_id=101, order_number="ORD-000101", status="new")
    result = await update_order(order=order, data=AdminOrderUpdateRequest(comment="Новый комментарий"))

    assert "admin:orders:*" in result.redis_service.deleted_patterns
    assert "orders:my:1:*" in result.redis_service.deleted_patterns
    assert "profile:orders:1:*" in result.redis_service.deleted_patterns
    assert "orders:detail:1:101" in result.redis_service.deleted
    assert "orders:status:1:101" in result.redis_service.deleted
    assert "profile:summary:1" in result.redis_service.deleted
    assert result.profile_cache_service.orders_invalidated is True
    assert result.profile_cache_service.summary_deleted is True
