from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError, OneCIntegrationDisabledError, OneCSyncAlreadyRunningError, OneCSyncError
from source.schemas.pydantic.one_c import AdminOneCLogsQueryParams, AdminOneCOrderSyncRequest, AdminOneCSyncRequest, OneCImportResultResponse, OneCPriceImportRequest, OneCProductImportRequest, OneCStockImportRequest
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
        self.permissions = permissions if permissions is not None else ["admin:integration_1c:sync", "admin:integration_1c:read"]

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
    def __init__(self, *, active_count: int = 0) -> None:
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.next_id = 1001
        self.active_count = active_count

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

    async def count_active(self, *, session):
        return self.active_count


class FakeIntegrationLogRepository:
    def __init__(self, logs: list | None = None) -> None:
        self.logs: list = logs if logs is not None else []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)

    async def get_list(self, *, session, query: AdminOneCLogsQueryParams):
        logs = self._filter(query=query)
        return logs[(query.page - 1) * query.limit : query.page * query.limit]

    async def count(self, *, session, query: AdminOneCLogsQueryParams):
        return len(self._filter(query=query))

    async def get_last_success(self, *, session):
        logs = [log for log in self.logs if log.system == "1c" and log.status == "success"]
        return max(logs, key=lambda log: (log.created_date, log.id), default=None)

    async def get_last_error(self, *, session):
        logs = [log for log in self.logs if log.system == "1c" and log.status == "error"]
        return max(logs, key=lambda log: (log.created_date, log.id), default=None)

    async def get_last_success_by_entity_type(self, *, session, entity_type: str):
        entity_map = {
            "categories": {"categories"},
            "products": {"products"},
            "prices": {"prices", "product_prices"},
            "stocks": {"stocks", "product_stocks"},
            "images": {"images", "product_images"},
            "orders": {"orders", "order"},
        }
        logs = [
            log
            for log in self.logs
            if log.system == "1c" and log.status == "success" and log.entity_type in entity_map[entity_type]
        ]
        return max(logs, key=lambda log: (log.created_date, log.id), default=None)

    def _filter(self, *, query: AdminOneCLogsQueryParams):
        logs = [log for log in self.logs if log.system == "1c"]
        if query.direction == "inbound":
            logs = [log for log in logs if log.entity_type not in {"orders", "order"}]
        if query.direction == "outbound":
            logs = [log for log in logs if log.entity_type in {"orders", "order"}]
        if query.entity_type is not None:
            entity_map = {
                "categories": {"categories"},
                "products": {"products"},
                "prices": {"prices", "product_prices"},
                "stocks": {"stocks", "product_stocks"},
                "images": {"images", "product_images"},
                "orders": {"orders", "order"},
            }
            logs = [log for log in logs if log.entity_type in entity_map[query.entity_type]]
        if query.status is not None:
            logs = [log for log in logs if log.status == query.status]
        if query.date_from is not None:
            logs = [log for log in logs if log.created_date >= query.date_from]
        if query.date_to is not None:
            logs = [log for log in logs if log.created_date <= query.date_to]
        if query.q is not None:
            q = query.q.lower()
            logs = [
                log
                for log in logs
                if q in log.action.lower()
                or q in (log.error_message or "").lower()
                or q in str(log.entity_id)
                or q in str(log.request_payload).lower()
                or q in str(log.response_payload).lower()
            ]
        return sorted(logs, key=lambda log: (log.created_date, log.id), reverse=True)


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


class FakeAdminOneCIntegrationCacheService:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.set_calls: list[dict] = []
        self.status_response = None
        self.set_status_calls: list[dict] = []

    async def get_status(self, *, redis_service):
        return self.status_response

    async def set_status(self, *, redis_service, response, ttl_seconds: int) -> None:
        self.status_response = response
        self.set_status_calls.append({"ttl_seconds": ttl_seconds})

    async def get_logs(self, *, redis_service, query_hash: str):
        return self.values.get(query_hash)

    async def set_logs(self, *, redis_service, query_hash: str, response, ttl_seconds: int) -> None:
        self.values[query_hash] = response
        self.set_calls.append({"query_hash": query_hash, "ttl_seconds": ttl_seconds})


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


def build_integration_log(
    *,
    log_id: int,
    entity_type: str = "products",
    status: str = "success",
    action: str = "inbound_import",
    error_message: str | None = None,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    created_date: datetime | None = None,
):
    return SimpleNamespace(
        id=log_id,
        system="1c",
        entity_type=entity_type,
        entity_id=log_id,
        action=action,
        status=status,
        error_message=error_message,
        request_payload=request_payload,
        response_payload=response_payload,
        created_date=created_date or datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=log_id),
    )


def build_config(*, sync_enabled: bool = True, api_url: str = "https://1c.example.ru/api"):
    return SimpleNamespace(
        one_c=SimpleNamespace(
            sync_enabled=sync_enabled,
            api_url=api_url,
            sync_lock_ttl_seconds=1800,
            health_timeout_seconds=5,
        ),
    )


class FakeOneCIntegrationService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.timeout_values: list[int] = []

    async def health_check(self, *, timeout_seconds: int) -> None:
        self.timeout_values.append(timeout_seconds)
        if self.error is not None:
            raise self.error


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


def build_logs_dependencies(**overrides):
    logs = [
        build_integration_log(log_id=1, entity_type="products", status="success", response_payload={"created": 20, "updated": 100, "errors": []}),
        build_integration_log(log_id=2, entity_type="product_prices", status="partial", response_payload={"updated": 10, "errors": [{"message": "bad price"}]}),
        build_integration_log(log_id=3, entity_type="orders", status="error", action="manual_sync_order", error_message="1C timeout", request_payload={"external_id": "order-ext-3"}),
    ]
    deps = {
        "session": object(),
        "redis_service": object(),
        "user": build_user(),
        "query": AdminOneCLogsQueryParams(),
        "permission_service": FakePermissionService(permissions=["admin:integration_1c:read"]),
        "integration_log_repository": FakeIntegrationLogRepository(logs),
        "admin_one_c_integration_cache_service": FakeAdminOneCIntegrationCacheService(),
    }
    deps.update(overrides)
    return deps


def build_status_dependencies(**overrides):
    base_date = datetime(2026, 5, 12, 10, 0, 0)
    logs = [
        build_integration_log(log_id=1, entity_type="products", status="success", created_date=base_date),
        build_integration_log(log_id=2, entity_type="product_prices", status="success", created_date=base_date + timedelta(minutes=10)),
        build_integration_log(log_id=3, entity_type="product_stocks", status="success", created_date=base_date + timedelta(minutes=20)),
        build_integration_log(log_id=4, entity_type="orders", status="success", created_date=base_date + timedelta(minutes=30)),
        build_integration_log(log_id=5, entity_type="orders", status="error", error_message="old error", created_date=base_date + timedelta(minutes=40)),
    ]
    deps = {
        "session": object(),
        "redis_service": object(),
        "user": build_user(),
        "config": build_config(),
        "permission_service": FakePermissionService(permissions=["admin:integration_1c:read"]),
        "one_c_integration_service": FakeOneCIntegrationService(),
        "integration_log_repository": FakeIntegrationLogRepository(logs),
        "integration_job_repository": FakeIntegrationJobRepository(active_count=2),
        "admin_one_c_integration_cache_service": FakeAdminOneCIntegrationCacheService(),
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


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_success() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies()

    response = await service.get_logs(**deps)

    assert response.total == 3
    assert response.page == 1
    assert response.limit == 50
    assert response.pages == 1
    assert response.items[0].id == 3
    assert response.items[0].direction == "outbound"
    assert response.items[1].entity_type == "prices"
    assert response.items[2].created_count == 20
    assert response.items[2].updated_count == 100


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_filters_direction() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(query=AdminOneCLogsQueryParams(direction="outbound"))

    response = await service.get_logs(**deps)

    assert response.total == 1
    assert response.items[0].entity_type == "orders"


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_filters_entity_type() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(query=AdminOneCLogsQueryParams(entity_type="prices"))

    response = await service.get_logs(**deps)

    assert response.total == 1
    assert response.items[0].entity_type == "prices"


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_filters_status() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(query=AdminOneCLogsQueryParams(status="partial"))

    response = await service.get_logs(**deps)

    assert response.total == 1
    assert response.items[0].status == "partial"


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_filters_date_range() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(
        query=AdminOneCLogsQueryParams(
            date_from=datetime(2026, 5, 12, 10, 2, 0),
            date_to=datetime(2026, 5, 12, 10, 2, 30),
        ),
    )

    response = await service.get_logs(**deps)

    assert response.total == 1
    assert response.items[0].id == 2


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_searches_q() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(query=AdminOneCLogsQueryParams(q="order-ext-3"))

    response = await service.get_logs(**deps)

    assert response.total == 1
    assert response.items[0].id == 3


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_paginates() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(query=AdminOneCLogsQueryParams(page=2, limit=2))

    response = await service.get_logs(**deps)

    assert response.total == 3
    assert response.pages == 2
    assert [item.id for item in response.items] == [1]


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_without_permission_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(permission_service=FakePermissionService(permissions=[]))

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.get_logs(**deps)


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_does_not_return_secrets() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies(
        permission_service=FakePermissionService(permissions=["admin:integration_1c:read", "admin:integration_1c:read_raw"]),
        integration_log_repository=FakeIntegrationLogRepository(
            [
                build_integration_log(
                    log_id=10,
                    request_payload={"headers": {"Authorization": "Bearer secret-token"}, "password": "secret-password"},
                    response_payload={"api_token": "secret-token", "updated": 1},
                ),
            ],
        ),
    )

    response = await service.get_logs(**deps)

    dumped = response.model_dump()
    assert "secret-token" not in str(dumped)
    assert "secret-password" not in str(dumped)
    assert response.items[0].request_payload["headers"]["Authorization"] == "***"
    assert response.items[0].response_payload["api_token"] == "***"


@pytest.mark.asyncio
async def test_admin_one_c_get_logs_hides_raw_without_permission() -> None:
    service = AdminOneCIntegrationService()
    deps = build_logs_dependencies()

    response = await service.get_logs(**deps)

    assert response.items[0].request_payload is None
    assert response.items[0].response_payload is None


@pytest.mark.asyncio
async def test_admin_one_c_get_status_enabled_and_available() -> None:
    service = AdminOneCIntegrationService()
    deps = build_status_dependencies()

    response = await service.get_status(**deps)

    assert response.enabled is True
    assert response.available is True
    assert response.status == "ok"
    assert response.api_url_configured is True
    assert response.active_jobs_count == 2
    assert response.last_success_sync_at == datetime(2026, 5, 12, 10, 30, 0)
    assert response.last_error_at == datetime(2026, 5, 12, 10, 40, 0)
    assert response.last_error_message == "old error"
    assert response.last_products_sync_at == datetime(2026, 5, 12, 10, 0, 0)
    assert response.last_prices_sync_at == datetime(2026, 5, 12, 10, 10, 0)
    assert response.last_stocks_sync_at == datetime(2026, 5, 12, 10, 20, 0)
    assert response.last_orders_sync_at == datetime(2026, 5, 12, 10, 30, 0)
    assert deps["one_c_integration_service"].timeout_values == [5]
    assert deps["admin_one_c_integration_cache_service"].set_status_calls == [{"ttl_seconds": 30}]


@pytest.mark.asyncio
async def test_admin_one_c_get_status_disabled() -> None:
    service = AdminOneCIntegrationService()
    deps = build_status_dependencies(config=build_config(sync_enabled=False, api_url=""))

    response = await service.get_status(**deps)

    assert response.enabled is False
    assert response.available is False
    assert response.status == "disabled"
    assert response.api_url_configured is False
    assert response.active_jobs_count == 0
    assert deps["one_c_integration_service"].timeout_values == []


@pytest.mark.asyncio
async def test_admin_one_c_get_status_unavailable() -> None:
    service = AdminOneCIntegrationService()
    deps = build_status_dependencies(one_c_integration_service=FakeOneCIntegrationService(error=OneCSyncError("1C unavailable")))

    response = await service.get_status(**deps)

    assert response.enabled is True
    assert response.available is False
    assert response.status == "error"
    assert response.last_error_message == "old error"


@pytest.mark.asyncio
async def test_admin_one_c_get_status_api_url_not_configured() -> None:
    service = AdminOneCIntegrationService()
    deps = build_status_dependencies(
        config=build_config(sync_enabled=True, api_url=""),
        integration_log_repository=FakeIntegrationLogRepository([]),
    )

    response = await service.get_status(**deps)

    assert response.enabled is True
    assert response.available is False
    assert response.status == "error"
    assert response.api_url_configured is False
    assert response.last_error_message == "1C API URL is not configured"
    assert deps["one_c_integration_service"].timeout_values == []


@pytest.mark.asyncio
async def test_admin_one_c_get_status_does_not_return_token() -> None:
    service = AdminOneCIntegrationService()
    deps = build_status_dependencies(
        one_c_integration_service=FakeOneCIntegrationService(error=OneCSyncError("secret-token unavailable")),
        integration_log_repository=FakeIntegrationLogRepository([]),
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(settings.one_c, "api_token", "secret-token")
    try:
        response = await service.get_status(**deps)
    finally:
        monkeypatch.undo()

    assert "secret-token" not in str(response.model_dump())
    assert response.last_error_message == "*** unavailable"


@pytest.mark.asyncio
async def test_admin_one_c_get_status_cache_works() -> None:
    service = AdminOneCIntegrationService()
    cache_service = FakeAdminOneCIntegrationCacheService()
    cache_service.status_response = build_status_dependencies()["admin_one_c_integration_cache_service"].status_response
    cached_response = await service.get_status(**build_status_dependencies()) 
    cache_service.status_response = cached_response
    deps = build_status_dependencies(
        admin_one_c_integration_cache_service=cache_service,
        one_c_integration_service=FakeOneCIntegrationService(error=AssertionError("health should not be called")),
    )

    response = await service.get_status(**deps)

    assert response == cached_response
    assert cache_service.set_status_calls == []


@pytest.mark.asyncio
async def test_admin_one_c_get_status_without_permission_error() -> None:
    service = AdminOneCIntegrationService()
    deps = build_status_dependencies(permission_service=FakePermissionService(permissions=[]))

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.get_status(**deps)
