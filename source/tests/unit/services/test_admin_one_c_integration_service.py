from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError, OneCIntegrationDisabledError, OneCSyncAlreadyRunningError, OneCSyncError
from source.schemas.pydantic.one_c import AdminOneCOrderSyncRequest, AdminOneCSyncRequest, OneCImportResultResponse, OneCPriceImportRequest, OneCProductImportRequest, OneCStockImportRequest
from source.services.one_c import AdminOneCIntegrationService, IntegrationJobService


class FakeCommiter:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakePermissionService:
    def __init__(self, permissions: list[str] | None = None) -> None:
        self.permissions = permissions if permissions is not None else ["admin:integration_1c:sync"]

    def get_user_permissions(self, *, role) -> list[str]:
        return self.permissions


class FakeRedisLockService:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.acquire_calls: list[dict] = []
        self.release_calls: list[dict] = []

    async def acquire(self, *, redis_service, key: str, ttl_seconds: int) -> bool:
        self.acquire_calls.append({"key": key, "ttl_seconds": ttl_seconds})
        return self.acquired

    async def release(self, *, redis_service, key: str) -> None:
        self.release_calls.append({"key": key})


class FakeOneCClient:
    def __init__(self, *, error: Exception | None = None, order_errors: set[int] | None = None) -> None:
        self.error = error
        self.order_errors = order_errors or set()
        self.full_sync_values: list[bool] = []
        self.price_full_sync_values: list[bool] = []
        self.stock_full_sync_values: list[bool] = []
        self.synced_order_payloads: list[dict] = []

    async def sync_order(self, *, payload: dict) -> dict:
        self.synced_order_payloads.append(payload)
        if payload["id"] in self.order_errors:
            raise OneCSyncError("1C unavailable")
        return {"external_1c_id": f"1c-{payload['id']}"}

    async def fetch_products(self, *, full_sync: bool = False):
        self.full_sync_values.append(full_sync)
        if self.error is not None:
            raise self.error
        return OneCProductImportRequest(items=[])

    async def fetch_prices(self, *, full_sync: bool = False):
        self.price_full_sync_values.append(full_sync)
        if self.error is not None:
            raise self.error
        return OneCPriceImportRequest(items=[])

    async def fetch_stocks(self, *, full_sync: bool = False):
        self.stock_full_sync_values.append(full_sync)
        if self.error is not None:
            raise self.error
        return OneCStockImportRequest(items=[])


class FakeOneCImportService:
    def __init__(self) -> None:
        self.calls = 0
        self.price_calls = 0
        self.stock_calls = 0

    async def import_products(self, **kwargs):
        self.calls += 1
        return OneCImportResultResponse(created=20, updated=100, errors=[])

    async def import_prices(self, **kwargs):
        self.price_calls += 1
        return OneCImportResultResponse(updated=100, errors=[])

    async def import_stocks(self, **kwargs):
        self.stock_calls += 1
        return OneCImportResultResponse(updated=100, errors=[])


class FakeIntegrationJobRepository:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.next_id = 1001

    async def create(self, *, session, **data):
        self.created.append(data)
        job = SimpleNamespace(id=self.next_id, **data)
        self.next_id += 1
        return job

    async def update_status(self, *, session, job, **data):
        self.updated.append(data)
        for field, value in data.items():
            setattr(job, field, value)
        return job


class FakeIntegrationLogRepository:
    def __init__(self) -> None:
        self.logs: list[dict] = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)


class FakeCacheService:
    def __init__(self) -> None:
        self.invalidated = 0
        self.invalidated_by_stock_changes = 0
        self.invalidated_low_stock = 0

    async def invalidate_all(self, *, redis_service) -> None:
        self.invalidated += 1

    async def invalidate_by_stock_changes(self, *, redis_service, products: list) -> None:
        self.invalidated_by_stock_changes += 1

    async def invalidate_low_stock(self, *, redis_service) -> None:
        self.invalidated_low_stock += 1


class FakeOrderCacheService:
    def __init__(self) -> None:
        self.invalidated_all = 0

    async def invalidate_all(self, *, redis_service) -> None:
        self.invalidated_all += 1


class FakeAdminOrderCacheService:
    def __init__(self) -> None:
        self.invalidated_all = 0

    async def invalidate_all(self, *, redis_service) -> None:
        self.invalidated_all += 1


class FakeOrderPayloadBuilder:
    def build(self, *, order, order_items, products_by_id, address, pickup_point, payment, delivery_time_slot):
        return SimpleNamespace(model_dump=lambda mode=None: {"id": order.id, "order_number": order.order_number})


class FakeOrderRepository:
    def __init__(self, orders: list | None = None) -> None:
        self.orders = orders if orders is not None else [build_order(order_id=101), build_order(order_id=102)]
        self.pending_calls: list[dict] = []
        self.error_calls: list[dict] = []
        self.success_updates: list[int] = []
        self.error_updates: list[int] = []

    async def get_pending_sync(self, *, session, limit: int, sync_status: str | None = None):
        self.pending_calls.append({"limit": limit, "sync_status": sync_status})
        return [order for order in self.orders if order.sync_status in {"pending", "pending_update", "pending_cancel"}][:limit]

    async def get_error_sync(self, *, session, limit: int):
        self.error_calls.append({"limit": limit})
        return [order for order in self.orders if order.sync_status == "error"][:limit]

    async def update_sync_success(self, *, session, order, external_1c_id: str | None, last_sync_at):
        order.sync_status = "synced"
        order.external_1c_id = external_1c_id
        order.sync_error = None
        order.last_sync_at = last_sync_at
        self.success_updates.append(order.id)
        return order

    async def update_sync_error(self, *, session, order, sync_error: str, sync_error_code: str | None, last_sync_at):
        order.sync_status = "error"
        order.sync_error = sync_error
        order.sync_error_code = sync_error_code
        order.last_sync_at = last_sync_at
        self.error_updates.append(order.id)
        return order


class FakeOrderItemRepository:
    async def get_by_order_ids(self, *, session, order_ids: list[int]):
        return []


class FakePaymentRepository:
    async def get_by_order_ids(self, *, session, order_ids: list[int]):
        return []


class FakeAddressRepository:
    async def get_by_ids(self, *, session, address_ids: list[int]):
        return []


class FakePickupPointRepository:
    async def get_by_ids(self, *, session, pickup_point_ids: list[int]):
        return []


class FakeDeliveryTimeSlotRepository:
    async def get_by_ids(self, *, session, slot_ids: list[int]):
        return []


class FakeProductRepository:
    async def get_by_ids(self, *, session, product_ids: list[int]):
        return []


class FakeDiscountCacheService:
    def __init__(self) -> None:
        self.invalidated_products = 0

    async def invalidate_products(self, *, redis_service) -> None:
        self.invalidated_products += 1


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False)


def build_order(*, order_id: int, sync_status: str = "pending"):
    return SimpleNamespace(
        id=order_id,
        order_number=f"ORD-{order_id}",
        sync_status=sync_status,
        external_1c_id=None,
        sync_error=None,
        sync_error_code=None,
        last_sync_at=None,
        address_id=None,
        pickup_point_id=None,
        delivery_time_slot_id=None,
    )


def build_config(*, sync_enabled: bool = True, api_url: str = "https://1c.example.ru/api"):
    return SimpleNamespace(
        one_c=SimpleNamespace(
            sync_enabled=sync_enabled,
            api_url=api_url,
            sync_lock_ttl_seconds=1800,
        ),
    )


def build_dependencies(**overrides):
    deps = {
        "session": object(),
        "redis_service": object(),
        "user": build_user(),
        "data": AdminOneCSyncRequest(full_sync=False),
        "commiter": FakeCommiter(),
        "config": build_config(),
        "permission_service": FakePermissionService(),
        "redis_lock_service": FakeRedisLockService(),
        "one_c_client": FakeOneCClient(),
        "one_c_import_service": FakeOneCImportService(),
        "product_sync_service": object(),
        "slug_service": object(),
        "integration_job_service": IntegrationJobService(),
        "integration_log_service": object(),
        "integration_job_repository": FakeIntegrationJobRepository(),
        "integration_log_repository": FakeIntegrationLogRepository(),
        "product_repository": object(),
        "category_repository": object(),
        "product_cache_service": FakeCacheService(),
        "admin_product_cache_service": FakeCacheService(),
        "category_cache_service": FakeCacheService(),
    }
    deps.update(overrides)
    return deps


def build_price_dependencies(**overrides):
    deps = {
        "session": object(),
        "redis_service": object(),
        "user": build_user(),
        "data": AdminOneCSyncRequest(full_sync=False),
        "commiter": FakeCommiter(),
        "config": build_config(),
        "permission_service": FakePermissionService(),
        "redis_lock_service": FakeRedisLockService(),
        "one_c_client": FakeOneCClient(),
        "one_c_import_service": FakeOneCImportService(),
        "product_price_sync_service": object(),
        "integration_job_service": IntegrationJobService(),
        "integration_log_service": object(),
        "integration_job_repository": FakeIntegrationJobRepository(),
        "integration_log_repository": FakeIntegrationLogRepository(),
        "product_repository": object(),
        "product_price_history_repository": object(),
        "product_cache_service": FakeCacheService(),
        "cart_cache_service": FakeCacheService(),
        "discount_cache_service": FakeDiscountCacheService(),
        "admin_product_cache_service": FakeCacheService(),
    }
    deps.update(overrides)
    return deps


def build_stock_dependencies(**overrides):
    deps = {
        "session": object(),
        "redis_service": object(),
        "user": build_user(),
        "data": AdminOneCSyncRequest(full_sync=False),
        "commiter": FakeCommiter(),
        "config": build_config(),
        "permission_service": FakePermissionService(),
        "redis_lock_service": FakeRedisLockService(),
        "one_c_client": FakeOneCClient(),
        "one_c_import_service": FakeOneCImportService(),
        "product_stock_sync_service": object(),
        "stock_movement_service": object(),
        "integration_job_service": IntegrationJobService(),
        "integration_log_service": object(),
        "integration_job_repository": FakeIntegrationJobRepository(),
        "integration_log_repository": FakeIntegrationLogRepository(),
        "product_repository": object(),
        "stock_movement_repository": object(),
        "product_cache_service": FakeCacheService(),
        "cart_cache_service": FakeCacheService(),
        "admin_dashboard_cache_service": FakeCacheService(),
        "admin_product_cache_service": FakeCacheService(),
    }
    deps.update(overrides)
    return deps


def build_order_dependencies(**overrides):
    deps = {
        "session": object(),
        "redis_service": object(),
        "user": build_user(),
        "data": AdminOneCOrderSyncRequest(limit=50, only_errors=False),
        "commiter": FakeCommiter(),
        "config": build_config(),
        "permission_service": FakePermissionService(),
        "redis_lock_service": FakeRedisLockService(),
        "one_c_client": FakeOneCClient(),
        "order_payload_builder": FakeOrderPayloadBuilder(),
        "integration_job_service": IntegrationJobService(),
        "integration_job_repository": FakeIntegrationJobRepository(),
        "integration_log_repository": FakeIntegrationLogRepository(),
        "order_repository": FakeOrderRepository(),
        "order_item_repository": FakeOrderItemRepository(),
        "payment_repository": FakePaymentRepository(),
        "address_repository": FakeAddressRepository(),
        "pickup_point_repository": FakePickupPointRepository(),
        "delivery_time_slot_repository": FakeDeliveryTimeSlotRepository(),
        "product_repository": FakeProductRepository(),
        "admin_order_cache_service": FakeAdminOrderCacheService(),
        "order_cache_service": FakeOrderCacheService(),
    }
    deps.update(overrides)
    return deps


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_success() -> None:
    service = AdminOneCIntegrationService()
    deps = build_dependencies(data=AdminOneCSyncRequest(full_sync=True))

    response = await service.sync_products(**deps)

    assert response.status == "success"
    assert response.job_id == 1001
    assert response.created == 20
    assert response.updated == 100
    assert deps["one_c_client"].full_sync_values == [True]
    assert deps["one_c_import_service"].calls == 1
    assert deps["redis_lock_service"].release_calls


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_disabled_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_dependencies(config=build_config(sync_enabled=False))

    with pytest.raises(OneCIntegrationDisabledError):
        await service.sync_products(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_existing_lock_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_dependencies(redis_lock_service=FakeRedisLockService(acquired=False))

    with pytest.raises(OneCSyncAlreadyRunningError):
        await service.sync_products(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_without_permission_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_dependencies(permission_service=FakePermissionService(permissions=[]))

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.sync_products(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_creates_job_and_log() -> None:
    service = AdminOneCIntegrationService()
    deps = build_dependencies()

    await service.sync_products(**deps)

    assert deps["integration_job_repository"].created[0]["type"] == "products"
    assert deps["integration_job_repository"].created[0]["status"] == "started"
    assert deps["integration_job_repository"].updated[-1]["status"] == "success"
    assert [log["action"] for log in deps["integration_log_repository"].logs] == [
        "manual_sync_started",
        "manual_sync_finished",
    ]


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_invalidates_cache() -> None:
    service = AdminOneCIntegrationService()
    deps = build_dependencies()

    await service.sync_products(**deps)

    assert deps["product_cache_service"].invalidated == 1
    assert deps["admin_product_cache_service"].invalidated == 1
    assert deps["category_cache_service"].invalidated == 1


@pytest.mark.asyncio
async def test_admin_one_c_sync_products_does_not_return_api_token(monkeypatch) -> None:
    service = AdminOneCIntegrationService()
    monkeypatch.setattr(settings.one_c, "api_token", "secret-token")
    deps = build_dependencies(one_c_client=FakeOneCClient(error=OneCSyncError("secret-token unavailable")))

    with pytest.raises(OneCSyncError) as exc_info:
        await service.sync_products(**deps)

    assert "secret-token" not in str(exc_info.value)
    assert "secret-token" not in deps["integration_log_repository"].logs[-1]["error_message"]


@pytest.mark.asyncio
async def test_admin_one_c_sync_prices_success() -> None:
    service = AdminOneCIntegrationService()
    deps = build_price_dependencies(data=AdminOneCSyncRequest(full_sync=True))

    response = await service.sync_prices(**deps)

    assert response.status == "success"
    assert response.job_id == 1001
    assert response.updated == 100
    assert response.errors == []
    assert deps["one_c_client"].price_full_sync_values == [True]
    assert deps["one_c_import_service"].price_calls == 1
    assert deps["redis_lock_service"].release_calls == [{"key": "integration:1c:lock:prices"}]


@pytest.mark.asyncio
async def test_admin_one_c_sync_prices_existing_lock_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_price_dependencies(redis_lock_service=FakeRedisLockService(acquired=False))

    with pytest.raises(OneCSyncAlreadyRunningError):
        await service.sync_prices(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_prices_disabled_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_price_dependencies(config=build_config(sync_enabled=False))

    with pytest.raises(OneCIntegrationDisabledError):
        await service.sync_prices(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_prices_without_permission_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_price_dependencies(permission_service=FakePermissionService(permissions=[]))

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.sync_prices(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_prices_creates_job_and_log() -> None:
    service = AdminOneCIntegrationService()
    deps = build_price_dependencies()

    await service.sync_prices(**deps)

    assert deps["integration_job_repository"].created[0]["type"] == "prices"
    assert deps["integration_job_repository"].created[0]["status"] == "started"
    assert deps["integration_job_repository"].updated[-1]["status"] == "success"
    assert [log["action"] for log in deps["integration_log_repository"].logs] == [
        "manual_sync_started",
        "manual_sync_finished",
    ]
    assert deps["integration_log_repository"].logs[0]["entity_type"] == "product_prices"


@pytest.mark.asyncio
async def test_admin_one_c_sync_prices_invalidates_cache() -> None:
    service = AdminOneCIntegrationService()
    deps = build_price_dependencies()

    await service.sync_prices(**deps)

    assert deps["product_cache_service"].invalidated == 1
    assert deps["cart_cache_service"].invalidated == 1
    assert deps["discount_cache_service"].invalidated_products == 1
    assert deps["admin_product_cache_service"].invalidated == 1


@pytest.mark.asyncio
async def test_admin_one_c_sync_stocks_success() -> None:
    service = AdminOneCIntegrationService()
    deps = build_stock_dependencies(data=AdminOneCSyncRequest(full_sync=True))

    response = await service.sync_stocks(**deps)

    assert response.status == "success"
    assert response.job_id == 1001
    assert response.updated == 100
    assert response.errors == []
    assert deps["one_c_client"].stock_full_sync_values == [True]
    assert deps["one_c_import_service"].stock_calls == 1
    assert deps["redis_lock_service"].release_calls == [{"key": "integration:1c:lock:stocks"}]


@pytest.mark.asyncio
async def test_admin_one_c_sync_stocks_existing_lock_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_stock_dependencies(redis_lock_service=FakeRedisLockService(acquired=False))

    with pytest.raises(OneCSyncAlreadyRunningError):
        await service.sync_stocks(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_stocks_disabled_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_stock_dependencies(config=build_config(sync_enabled=False))

    with pytest.raises(OneCIntegrationDisabledError):
        await service.sync_stocks(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_stocks_without_permission_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_stock_dependencies(permission_service=FakePermissionService(permissions=[]))

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.sync_stocks(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_stocks_creates_job_and_log() -> None:
    service = AdminOneCIntegrationService()
    deps = build_stock_dependencies()

    await service.sync_stocks(**deps)

    assert deps["integration_job_repository"].created[0]["type"] == "stocks"
    assert deps["integration_job_repository"].created[0]["status"] == "started"
    assert deps["integration_job_repository"].updated[-1]["status"] == "success"
    assert [log["action"] for log in deps["integration_log_repository"].logs] == [
        "manual_sync_started",
        "manual_sync_finished",
    ]
    assert deps["integration_log_repository"].logs[0]["entity_type"] == "product_stocks"


@pytest.mark.asyncio
async def test_admin_one_c_sync_stocks_invalidates_low_stock_cache() -> None:
    service = AdminOneCIntegrationService()
    deps = build_stock_dependencies()

    await service.sync_stocks(**deps)

    assert deps["product_cache_service"].invalidated_by_stock_changes == 1
    assert deps["cart_cache_service"].invalidated == 1
    assert deps["admin_dashboard_cache_service"].invalidated_low_stock == 1
    assert deps["admin_product_cache_service"].invalidated == 1


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_pending_success() -> None:
    service = AdminOneCIntegrationService()
    deps = build_order_dependencies()

    response = await service.sync_orders(**deps)

    assert response.status == "success"
    assert response.job_id == 1001
    assert response.processed == 2
    assert response.synced == 2
    assert response.errors == 0
    assert deps["order_repository"].pending_calls == [{"limit": 50, "sync_status": None}]
    assert deps["order_repository"].success_updates == [101, 102]
    assert deps["one_c_client"].synced_order_payloads == [
        {"id": 101, "order_number": "ORD-101"},
        {"id": 102, "order_number": "ORD-102"},
    ]


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_only_errors_uses_error_orders() -> None:
    service = AdminOneCIntegrationService()
    order_repository = FakeOrderRepository([build_order(order_id=201, sync_status="error")])
    deps = build_order_dependencies(
        data=AdminOneCOrderSyncRequest(limit=10, only_errors=True),
        order_repository=order_repository,
    )

    response = await service.sync_orders(**deps)

    assert response.processed == 1
    assert response.synced == 1
    assert order_repository.pending_calls == []
    assert order_repository.error_calls == [{"limit": 10}]
    assert order_repository.success_updates == [201]


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_one_error_does_not_stop_others() -> None:
    service = AdminOneCIntegrationService()
    order_repository = FakeOrderRepository([build_order(order_id=301), build_order(order_id=302)])
    deps = build_order_dependencies(
        order_repository=order_repository,
        one_c_client=FakeOneCClient(order_errors={301}),
    )

    response = await service.sync_orders(**deps)

    assert response.processed == 2
    assert response.synced == 1
    assert response.errors == 1
    assert order_repository.error_updates == [301]
    assert order_repository.success_updates == [302]


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_existing_lock_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_order_dependencies(redis_lock_service=FakeRedisLockService(acquired=False))

    with pytest.raises(OneCSyncAlreadyRunningError):
        await service.sync_orders(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_disabled_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_order_dependencies(config=build_config(sync_enabled=False))

    with pytest.raises(OneCIntegrationDisabledError):
        await service.sync_orders(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_without_permission_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_order_dependencies(permission_service=FakePermissionService(permissions=[]))

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.sync_orders(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_invalidates_cache() -> None:
    service = AdminOneCIntegrationService()
    deps = build_order_dependencies()

    await service.sync_orders(**deps)

    assert deps["admin_order_cache_service"].invalidated_all == 1
    assert deps["order_cache_service"].invalidated_all == 1


@pytest.mark.asyncio
async def test_admin_one_c_sync_orders_creates_job_and_logs() -> None:
    service = AdminOneCIntegrationService()
    deps = build_order_dependencies()

    await service.sync_orders(**deps)

    assert deps["integration_job_repository"].created[0]["type"] == "orders"
    assert deps["integration_job_repository"].created[0]["status"] == "started"
    assert deps["integration_job_repository"].updated[-1]["status"] == "success"
    assert [log["action"] for log in deps["integration_log_repository"].logs] == [
        "manual_sync_started",
        "manual_sync_order",
        "manual_sync_order",
        "manual_sync_finished",
    ]
    assert deps["integration_log_repository"].logs[1]["entity_id"] == 101
