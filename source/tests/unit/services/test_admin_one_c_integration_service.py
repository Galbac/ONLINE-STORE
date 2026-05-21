from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError, OneCIntegrationDisabledError, OneCSyncAlreadyRunningError, OneCSyncError
from source.schemas.pydantic.one_c import AdminOneCSyncRequest, OneCImportResultResponse, OneCPriceImportRequest, OneCProductImportRequest, OneCStockImportRequest
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
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.full_sync_values: list[bool] = []
        self.price_full_sync_values: list[bool] = []
        self.stock_full_sync_values: list[bool] = []

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


class FakeDiscountCacheService:
    def __init__(self) -> None:
        self.invalidated_products = 0

    async def invalidate_products(self, *, redis_service) -> None:
        self.invalidated_products += 1


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False)


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
