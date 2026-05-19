from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.admin_dashboard import (
    AdminDashboardResponse,
    AdminSalesQueryParams,
    AdminSalesResponse,
    AdminSalesSeriesItem,
    AdminRecentOrderResponse,
    AdminPopularProductResponse,
)
from source.services.admin_auth import PermissionService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService


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

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FakeOrderRepository:
    def __init__(self, *, new_count: int = 7) -> None:
        self.new_count = new_count
        self.called = False

    async def get_dashboard_stats(self, *, session):
        self.called = True
        return SimpleNamespace(
            today_count=25,
            new_count=self.new_count,
            paid_today_count=18,
            sales_today_amount=Decimal("125000.00"),
        )

    async def get_dashboard_recent_orders(self, *, session, limit: int = 5):
        return [
            AdminRecentOrderResponse(
                id=101,
                order_number="ORD-000101",
                status="new",
                final_price=Decimal("3250.00"),
                created_at=datetime(2026, 5, 12, 10),
            ),
        ]

    async def get_sales_stats(self, *, session, query: AdminSalesQueryParams):
        if self.new_count == -1:
            series = [
                AdminSalesSeriesItem(date=date(2026, 5, 1), amount=Decimal("42000.00"), orders_count=10),
                AdminSalesSeriesItem(date=date(2026, 5, 2), amount=Decimal("83000.00"), orders_count=20),
            ]
        else:
            series = [
                AdminSalesSeriesItem(date=date(2026, 5, 1), amount=Decimal("125000.00"), orders_count=32),
            ]
        total_amount = sum((item.amount for item in series), Decimal("0.00"))
        orders_count = sum(item.orders_count for item in series)
        return AdminSalesResponse(
            date_from=query.date_from,
            date_to=query.date_to,
            group_by=query.group_by,
            total_amount=total_amount,
            orders_count=orders_count,
            average_order_value=total_amount / orders_count if orders_count else Decimal("0.00"),
            series=series,
        )


class FakeProductRepository:
    def __init__(self, *, low_stock_count: int = 12) -> None:
        self.low_stock_count = low_stock_count

    async def count_low_stock(self, *, session):
        return self.low_stock_count

    async def count_total_active(self, *, session):
        return 1050

    async def get_dashboard_popular_products(self, *, session, limit: int = 5):
        return [
            AdminPopularProductResponse(
                id=10,
                name="Яблоки",
                price=Decimal("120.00"),
                popularity=100,
            ),
        ]


class FakeUserRepository:
    async def count_customers(self, *, session):
        return 500


def build_user(*, role=UserRole.ADMIN, is_active: bool = True, is_deleted: bool = False):
    return SimpleNamespace(id=1, role=role, is_active=is_active, is_deleted=is_deleted)


async def get_summary(
    *,
    redis_service=None,
    user=None,
    order_repository=None,
    product_repository=None,
):
    return await AdminDashboardService().get_summary(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        permission_service=PermissionService(),
        order_repository=order_repository or FakeOrderRepository(),
        product_repository=product_repository or FakeProductRepository(),
        user_repository=FakeUserRepository(),
        admin_dashboard_cache_service=AdminDashboardCacheService(),
    )


async def get_sales(
    *,
    redis_service=None,
    user=None,
    order_repository=None,
    query=None,
):
    return await AdminDashboardService().get_sales(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        query=query or AdminSalesQueryParams(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)),
        permission_service=PermissionService(),
        order_repository=order_repository or FakeOrderRepository(),
        admin_dashboard_cache_service=AdminDashboardCacheService(),
    )


@pytest.mark.asyncio
async def test_admin_dashboard_success() -> None:
    response = await get_summary()

    assert response.orders.today_count == 25
    assert response.orders.new_count == 7
    assert response.sales.today_amount == Decimal("125000.00")
    assert response.products.low_stock_count == 12
    assert response.users.total == 500
    assert response.recent_orders[0].order_number == "ORD-000101"


@pytest.mark.asyncio
async def test_admin_dashboard_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminDashboardResponse(
        orders={"today_count": 1, "new_count": 1, "paid_today_count": 1},
        sales={"today_amount": Decimal("100.00"), "currency": "RUB"},
        products={"low_stock_count": 2, "total_active": 3},
        users={"total": 4},
        recent_orders=[],
        popular_products=[],
    )
    redis_service.values["admin:dashboard:summary"] = cached_response.model_dump_json()
    order_repository = FakeOrderRepository()

    response = await get_summary(redis_service=redis_service, order_repository=order_repository)

    assert response == cached_response
    assert order_repository.called is False


@pytest.mark.asyncio
async def test_admin_dashboard_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_summary(user=build_user(role=UserRole.CUSTOMER))


@pytest.mark.asyncio
async def test_admin_dashboard_blocked_user_error() -> None:
    with pytest.raises(InactiveUserError):
        await get_summary(user=build_user(is_active=False))


@pytest.mark.asyncio
async def test_admin_dashboard_new_orders_count() -> None:
    response = await get_summary(order_repository=FakeOrderRepository(new_count=9))

    assert response.orders.new_count == 9


@pytest.mark.asyncio
async def test_admin_dashboard_low_stock_count() -> None:
    response = await get_summary(product_repository=FakeProductRepository(low_stock_count=4))

    assert response.products.low_stock_count == 4


@pytest.mark.asyncio
async def test_admin_dashboard_response_is_cached() -> None:
    redis_service = FakeRedisService()

    await get_summary(redis_service=redis_service)

    assert "admin:dashboard:summary" in redis_service.values
    assert redis_service.ttls["admin:dashboard:summary"] == settings.admin_dashboard.cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_dashboard_sales_for_period() -> None:
    response = await get_sales()

    assert response.date_from == date(2026, 5, 1)
    assert response.date_to == date(2026, 5, 31)
    assert response.total_amount == Decimal("125000.00")
    assert response.orders_count == 32


@pytest.mark.asyncio
async def test_admin_dashboard_sales_group_by_day() -> None:
    response = await get_sales(query=AdminSalesQueryParams(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31), group_by="day"))

    assert response.group_by == "day"
    assert response.series[0].date == date(2026, 5, 1)


@pytest.mark.asyncio
async def test_admin_dashboard_sales_group_by_month() -> None:
    response = await get_sales(query=AdminSalesQueryParams(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31), group_by="month"))

    assert response.group_by == "month"


@pytest.mark.asyncio
async def test_admin_dashboard_sales_cancelled_orders_are_not_counted() -> None:
    response = await get_sales(order_repository=FakeOrderRepository(new_count=-1))

    assert response.total_amount == Decimal("125000.00")
    assert response.orders_count == 30


def test_admin_dashboard_sales_invalid_dates() -> None:
    with pytest.raises(ValidationError):
        AdminSalesQueryParams(date_from=date(2026, 6, 1), date_to=date(2026, 5, 1))


@pytest.mark.asyncio
async def test_admin_dashboard_sales_cache_works() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminSalesResponse(
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        group_by="day",
        total_amount=Decimal("100.00"),
        orders_count=2,
        average_order_value=Decimal("50.00"),
        series=[],
    )
    query = AdminSalesQueryParams(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
    from source.utils.query_hash import build_query_hash

    redis_service.values[f"admin:dashboard:sales:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()
    order_repository = FakeOrderRepository()

    response = await get_sales(redis_service=redis_service, order_repository=order_repository, query=query)

    assert response == cached_response
    assert order_repository.called is False


@pytest.mark.asyncio
async def test_admin_dashboard_sales_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_sales(user=build_user(role=UserRole.CONTENT_MANAGER))
