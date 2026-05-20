from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.schemas.pydantic.order import AdminOrderListItemResponse, AdminOrderListQueryParams, AdminOrderListResponse
from source.services.admin_auth import PermissionService
from source.services.admin_order import AdminOrderService
from source.services.order_cache import OrderCacheService


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.values = {key: value for key, value in self.values.items() if not key.startswith(pattern.rstrip("*"))}


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
        created_date=created_date or datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=order_id),
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
