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
    AdminLowStockProductResponse,
    AdminLowStockQueryParams,
    AdminLowStockResponse,
    AdminSalesQueryParams,
    AdminSalesResponse,
    AdminSalesSeriesItem,
    AdminRecentOrderResponse,
    AdminPopularProductResponse,
)
from source.services.admin_auth import PermissionService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.utils.query_hash import build_query_hash


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

    async def delete_by_pattern(self, pattern: str) -> None:
        prefix = pattern.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
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
    def __init__(self, *, low_stock_count: int = 12, products: list | None = None) -> None:
        self.low_stock_count = low_stock_count
        self.products = products or []
        self.low_stock_called = False

    async def count_low_stock(self, *, session, category_id: int | None = None):
        if not self.products:
            return self.low_stock_count
        return len(self._filter_low_stock(category_id=category_id))

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

    async def get_low_stock(self, *, session, query: AdminLowStockQueryParams):
        self.low_stock_called = True
        products = sorted(
            self._filter_low_stock(category_id=query.category_id),
            key=lambda product: (product.stock_quantity, product.name),
        )
        return [
            AdminLowStockProductResponse(
                id=product.id,
                name=product.name,
                sku=product.article,
                unit=product.unit,
                product_type=product.product_type,
                stock_quantity=product.stock_quantity,
                low_stock_threshold=product.min_quantity,
                is_available=product.is_available,
            )
            for product in products[query.offset : query.offset + query.limit]
        ]

    def _filter_low_stock(self, *, category_id: int | None = None):
        products = [
            product
            for product in self.products
            if product.is_active
            and not product.is_deleted
            and product.stock_quantity <= product.min_quantity
        ]
        if category_id is not None:
            products = [product for product in products if product.category_id == category_id]
        return products


class FakeUserRepository:
    async def count_customers(self, *, session):
        return 500


def build_user(*, role=UserRole.ADMIN, is_active: bool = True, is_deleted: bool = False):
    return SimpleNamespace(id=1, role=role, is_active=is_active, is_deleted=is_deleted)


def build_product(
    *,
    product_id: int,
    name: str,
    category_id: int = 10,
    stock_quantity: Decimal = Decimal("2"),
    min_quantity: Decimal = Decimal("5"),
    is_active: bool = True,
    is_deleted: bool = False,
):
    return SimpleNamespace(
        id=product_id,
        name=name,
        article=f"SKU-{product_id}",
        unit="kg",
        product_type="weight",
        stock_quantity=stock_quantity,
        min_quantity=min_quantity,
        is_available=True,
        is_active=is_active,
        is_deleted=is_deleted,
        category_id=category_id,
    )


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


async def get_low_stock(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    query=None,
):
    return await AdminDashboardService().get_low_stock_products(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        query=query or AdminLowStockQueryParams(),
        permission_service=PermissionService(),
        product_repository=product_repository or FakeProductRepository(),
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
async def test_admin_dashboard_low_stock_success() -> None:
    product_repository = FakeProductRepository(
        products=[
            build_product(product_id=55, name="Яблоки", stock_quantity=Decimal("2.5")),
            build_product(product_id=56, name="Молоко", stock_quantity=Decimal("10"), min_quantity=Decimal("5")),
        ],
    )

    response = await get_low_stock(product_repository=product_repository)

    assert response.total == 1
    assert response.limit == 50
    assert response.offset == 0
    assert response.items[0].id == 55
    assert response.items[0].sku == "SKU-55"
    assert response.items[0].low_stock_threshold == Decimal("5")


@pytest.mark.asyncio
async def test_admin_dashboard_low_stock_category_filter() -> None:
    response = await get_low_stock(
        query=AdminLowStockQueryParams(category_id=20),
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки", category_id=10),
                build_product(product_id=56, name="Груши", category_id=20),
            ],
        ),
    )

    assert response.total == 1
    assert response.items[0].id == 56


@pytest.mark.asyncio
async def test_admin_dashboard_low_stock_sorted_by_stock_quantity() -> None:
    response = await get_low_stock(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки", stock_quantity=Decimal("3")),
                build_product(product_id=56, name="Груши", stock_quantity=Decimal("1")),
                build_product(product_id=57, name="Бананы", stock_quantity=Decimal("2")),
            ],
        ),
    )

    assert [item.id for item in response.items] == [56, 57, 55]


@pytest.mark.asyncio
async def test_admin_dashboard_low_stock_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    query = AdminLowStockQueryParams(limit=10, offset=0, category_id=10)
    cached_response = AdminLowStockResponse(
        items=[
            AdminLowStockProductResponse(
                id=55,
                name="Яблоки",
                sku="APL-001",
                unit="kg",
                product_type="weight",
                stock_quantity=Decimal("2.5"),
                low_stock_threshold=Decimal("5"),
                is_available=True,
            ),
        ],
        total=1,
        limit=10,
        offset=0,
    )
    query_hash = build_query_hash(query.model_dump())
    redis_service.values[f"admin:dashboard:low_stock:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await get_low_stock(redis_service=redis_service, product_repository=product_repository, query=query)

    assert response == cached_response
    assert product_repository.low_stock_called is False


@pytest.mark.asyncio
async def test_admin_dashboard_low_stock_response_is_cached() -> None:
    redis_service = FakeRedisService()
    query = AdminLowStockQueryParams(limit=10, offset=0)

    await get_low_stock(
        redis_service=redis_service,
        query=query,
        product_repository=FakeProductRepository(products=[build_product(product_id=55, name="Яблоки")]),
    )

    cache_key = f"admin:dashboard:low_stock:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.admin_dashboard.low_stock_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_dashboard_low_stock_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_low_stock(user=build_user(role=UserRole.PICKER))


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
