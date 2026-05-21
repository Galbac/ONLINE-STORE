from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from source.api.api_v1.views.health import get_db_health, verify_internal_health_token
from source.config.settings import settings
from source.services.health import HealthService


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
        ),
    )


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
