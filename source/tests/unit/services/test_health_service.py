from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from source.api.api_v1.views.health import get_db_health, verify_internal_health_token
from source.api.api_v1.views.health import get_one_c_health, get_storage_health
from source.config.settings import settings
from source.config.settings import MediaSettings
from source.services.health import HealthService
from source.services.health_cache import HealthCacheService
from source.services.storage import LocalStorageProvider, StorageService


class FakeDatabaseHealthChecker:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.called = False

    async def check(self, *, session) -> None:
        self.called = True
        if self.fail is not None:
            raise self.fail


def build_config(*, protect: bool = False):
    return SimpleNamespace(
        app=SimpleNamespace(
            name="supermarket-api",
            version="1.0.0",
            environment="production",
            health_show_environment=False,
            health_db_timeout_seconds=3,
            health_protect_internal_endpoints=protect,
            health_internal_token="secret",
            health_storage_timeout_seconds=5,
            health_storage_check_write=False,
            health_1c_cache_ttl_seconds=30,
        ),
        media=SimpleNamespace(storage="local"),
    )


class FakeStorageService:
    def __init__(self, *, result=None, fail: Exception | None = None) -> None:
        self.result = result or {"available": True}
        self.fail = fail

    async def health_check(self, *, check_write: bool = False):
        if self.fail is not None:
            raise self.fail
        return self.result


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds


class FakeOneCIntegrationService:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.called = False

    async def health_check(self, *, timeout_seconds: int) -> None:
        self.called = True
        if self.fail is not None:
            raise self.fail


def test_health_service_returns_ok() -> None:
    response = HealthService().get_health(config=settings)

    assert response.status == "ok"


def test_health_service_returns_service_name() -> None:
    response = HealthService().get_health(config=settings)

    assert response.service


def test_health_service_does_not_require_db_or_redis() -> None:
    response = HealthService().get_health(config=settings)

    assert response.status == "ok"


def test_health_service_does_not_return_secrets() -> None:
    response = HealthService().get_health(config=settings)
    payload = response.model_dump_json()

    assert "password" not in payload.lower()
    assert "secret" not in payload.lower()
    assert "token" not in payload.lower()


@pytest.mark.asyncio
async def test_health_db_success_returns_ok() -> None:
    response = await HealthService().check_db(
        session=object(),
        config=build_config(),
        database_health_checker=FakeDatabaseHealthChecker(),
    )

    assert response.status == "ok"
    assert response.database == "postgresql"


@pytest.mark.asyncio
async def test_health_db_returns_latency_ms() -> None:
    response = await HealthService().check_db(
        session=object(),
        config=build_config(),
        database_health_checker=FakeDatabaseHealthChecker(),
    )

    assert response.latency_ms is not None
    assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_health_db_endpoint_error_returns_503() -> None:
    response = await get_db_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        session=object(),
        config=build_config(),
        health_service=HealthService(),
        database_health_checker=FakeDatabaseHealthChecker(fail=RuntimeError("connection string postgres://user:pass@db")),
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_health_db_does_not_return_connection_string() -> None:
    response = await get_db_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        session=object(),
        config=build_config(),
        health_service=HealthService(),
        database_health_checker=FakeDatabaseHealthChecker(fail=RuntimeError("postgres://user:pass@localhost/db")),
    )

    body = response.body.decode("utf-8")
    assert "postgres://" not in body
    assert "pass" not in body


def test_health_db_internal_token_required_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_internal_health_token(
            config=build_config(protect=True),
            authorization=None,
            x_internal_token=None,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_health_storage_local_available(tmp_path) -> None:
    config = build_config()
    config.media.storage = "local"
    config.app.health_storage_check_write = False
    media_settings = MediaSettings().model_copy(update={"storage": "local", "root": tmp_path})

    response = await HealthService().check_storage(
        config=config,
        storage_service=StorageService(media_settings),
    )

    assert response.status == "ok"
    assert response.storage_type == "local"
    assert response.readable is True
    assert response.writable is None


@pytest.mark.asyncio
async def test_health_storage_local_missing_directory_returns_503(tmp_path) -> None:
    config = build_config()
    config.media.storage = "local"
    missing_root = tmp_path / "missing"
    media_settings = MediaSettings().model_copy(update={"storage": "local", "root": missing_root})

    response = await get_storage_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        health_service=HealthService(),
        storage_service=StorageService(media_settings),
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_health_storage_external_available() -> None:
    config = build_config()
    config.media.storage = "external"

    response = await HealthService().check_storage(
        config=config,
        storage_service=FakeStorageService(result={"available": True}),
    )

    assert response.status == "ok"
    assert response.storage_type == "external"
    assert response.available is True
    assert response.latency_ms is not None


@pytest.mark.asyncio
async def test_health_storage_external_unavailable_returns_503() -> None:
    config = build_config()
    config.media.storage = "external"

    response = await get_storage_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        health_service=HealthService(),
        storage_service=FakeStorageService(fail=RuntimeError("STORAGE_SECRET_KEY=secret")),
    )

    assert response.status_code == 503
    assert "secret" not in response.body.decode("utf-8").lower()


@pytest.mark.asyncio
async def test_health_storage_does_not_return_secrets() -> None:
    config = build_config()
    config.media.storage = "external"

    response = await HealthService().check_storage(
        config=config,
        storage_service=FakeStorageService(result={"available": True}),
    )

    payload = response.model_dump_json()
    assert "storage_access_key" not in payload.lower()
    assert "storage_secret_key" not in payload.lower()
    assert "secret" not in payload.lower()


@pytest.mark.asyncio
async def test_health_storage_write_check_removes_temp_file(tmp_path) -> None:
    config = build_config()
    config.media.storage = "local"
    config.app.health_storage_check_write = True
    media_settings = MediaSettings().model_copy(update={"storage": "local", "root": tmp_path})

    response = await HealthService().check_storage(
        config=config,
        storage_service=StorageService(media_settings),
    )

    assert response.writable is True
    assert list(tmp_path.glob(".health-*.tmp")) == []


@pytest.mark.asyncio
async def test_health_one_c_enabled_available() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=True, api_url="https://1c.example/api", health_timeout_seconds=5)

    response = await HealthService().check_1c(
        config=config,
        one_c_integration_service=FakeOneCIntegrationService(),
    )

    assert response.status == "ok"
    assert response.enabled is True
    assert response.available is True
    assert response.latency_ms is not None


@pytest.mark.asyncio
async def test_health_one_c_disabled_returns_disabled() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=False, api_url="", health_timeout_seconds=5)

    response = await HealthService().check_1c(
        config=config,
        one_c_integration_service=FakeOneCIntegrationService(),
    )

    assert response.status == "disabled"
    assert response.enabled is False
    assert response.available is False


@pytest.mark.asyncio
async def test_health_one_c_missing_url_returns_503() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=True, api_url="", health_timeout_seconds=5)

    response = await get_one_c_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        redis_service=FakeRedisService(),
        health_service=HealthService(),
        health_cache_service=HealthCacheService(),
        one_c_integration_service=FakeOneCIntegrationService(),
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_health_one_c_unavailable_returns_503() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=True, api_url="https://1c.example/api", health_timeout_seconds=5)

    response = await get_one_c_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        redis_service=FakeRedisService(),
        health_service=HealthService(),
        health_cache_service=HealthCacheService(),
        one_c_integration_service=FakeOneCIntegrationService(fail=RuntimeError("ONE_C_API_TOKEN=secret")),
    )

    assert response.status_code == 503
    assert "secret" not in response.body.decode("utf-8").lower()


@pytest.mark.asyncio
async def test_health_one_c_token_not_returned() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=True, api_url="https://1c.example/api", health_timeout_seconds=5)

    response = await HealthService().check_1c(
        config=config,
        one_c_integration_service=FakeOneCIntegrationService(),
    )

    assert "token" not in response.model_dump_json().lower()
    assert "secret" not in response.model_dump_json().lower()


@pytest.mark.asyncio
async def test_health_one_c_cache_works() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=True, api_url="https://1c.example/api", health_timeout_seconds=5)
    redis_service = FakeRedisService()
    one_c_service = FakeOneCIntegrationService()

    first = await get_one_c_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        redis_service=redis_service,
        health_service=HealthService(),
        health_cache_service=HealthCacheService(),
        one_c_integration_service=one_c_service,
    )
    one_c_service.called = False
    second = await get_one_c_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        redis_service=redis_service,
        health_service=HealthService(),
        health_cache_service=HealthCacheService(),
        one_c_integration_service=one_c_service,
    )

    assert first.status == "ok"
    assert second.status == "ok"
    assert one_c_service.called is False
    assert redis_service.ttls["health:1c"] == config.app.health_1c_cache_ttl_seconds


@pytest.mark.asyncio
async def test_health_one_c_timeout_returns_503() -> None:
    config = build_config()
    config.one_c = SimpleNamespace(sync_enabled=True, api_url="https://1c.example/api", health_timeout_seconds=0.001)

    class SlowOneCIntegrationService:
        async def health_check(self, *, timeout_seconds: int) -> None:
            import asyncio

            await asyncio.sleep(0.01)

    response = await get_one_c_health.__dishka_orig_func__(
        authorization=None,
        x_internal_token=None,
        config=config,
        redis_service=FakeRedisService(),
        health_service=HealthService(),
        health_cache_service=HealthCacheService(),
        one_c_integration_service=SlowOneCIntegrationService(),
    )

    assert response.status_code == 503
