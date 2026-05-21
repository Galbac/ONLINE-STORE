from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.schemas.pydantic.delivery import AdminDeliverySettingsResponse
from source.services.admin_auth import PermissionService
from source.services.admin_delivery import AdminDeliveryService
from source.services.admin_delivery_cache import AdminDeliveryCacheService


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class FakeDeliverySettingsRepository:
    def __init__(self, delivery_settings=None) -> None:
        self.delivery_settings = delivery_settings
        self.get_or_create_calls = 0
        self.created_default = False

    async def get_or_create_default(self, *, session):
        self.get_or_create_calls += 1
        if self.delivery_settings is not None:
            return self.delivery_settings, False
        self.created_default = True
        self.delivery_settings = build_delivery_settings(
            pickup_comment="Самовывоз доступен из выбранных магазинов",
        )
        return self.delivery_settings, True


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
        is_deleted=False,
        is_blocked=False,
    )


def build_delivery_settings(
    *,
    delivery_enabled: bool = True,
    pickup_enabled: bool = True,
    pickup_comment: str = "Самовывоз доступен из выбранных магазинов",
):
    return SimpleNamespace(
        id=1,
        delivery_enabled=delivery_enabled,
        pickup_enabled=pickup_enabled,
        min_order_amount=Decimal("1000.00"),
        base_price=Decimal("250.00"),
        free_from_amount=Decimal("3000.00"),
        has_time_slots=True,
        delivery_description="Доставка по городу",
        pickup_description=pickup_comment,
        default_city="Москва",
        currency="RUB",
        created_date=datetime(2026, 5, 12, 9, 0, 0),
        updated_date=datetime(2026, 5, 12, 10, 0, 0),
        internal_secret="hidden",
    )


async def get_settings(
    *,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    commiter = commiter or FakeCommiter()
    repository = repository or FakeDeliverySettingsRepository(build_delivery_settings())
    response = await AdminDeliveryService().get_settings(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        commiter=commiter,
        permission_service=PermissionService(),
        admin_delivery_cache_service=AdminDeliveryCacheService(),
        delivery_settings_repository=repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
        commiter=commiter,
    )


@pytest.mark.asyncio
async def test_admin_delivery_settings_from_postgres_success() -> None:
    result = await get_settings()

    assert result.response.delivery_enabled is True
    assert result.response.pickup_enabled is True
    assert result.response.min_order_amount == Decimal("1000.00")
    assert result.response.base_delivery_price == Decimal("250.00")
    assert result.response.free_delivery_from == Decimal("3000.00")
    assert result.response.time_slots_enabled is True
    assert result.response.delivery_comment == "Доставка по городу"
    assert result.response.pickup_comment == "Самовывоз доступен из выбранных магазинов"
    assert result.response.default_city == "Москва"
    assert result.response.currency == "RUB"
    assert result.response.updated_at == datetime(2026, 5, 12, 10, 0, 0)


@pytest.mark.asyncio
async def test_admin_delivery_settings_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminDeliverySettingsResponse(
        delivery_enabled=False,
        pickup_enabled=True,
        min_order_amount=Decimal("1500.00"),
        base_delivery_price=Decimal("300.00"),
        free_delivery_from=Decimal("4000.00"),
        time_slots_enabled=False,
        delivery_comment="Из кеша",
        pickup_comment="Самовывоз",
        default_city="Казань",
        currency="RUB",
        updated_at=datetime(2026, 5, 12, 10, 0, 0),
    )
    redis_service.values["admin:delivery:settings"] = cached_response.model_dump_json()
    repository = FakeDeliverySettingsRepository(build_delivery_settings())

    result = await get_settings(redis_service=redis_service, repository=repository)

    assert result.response == cached_response
    assert repository.get_or_create_calls == 0


@pytest.mark.asyncio
async def test_admin_delivery_settings_default_values_when_missing() -> None:
    commiter = FakeCommiter()
    result = await get_settings(repository=FakeDeliverySettingsRepository(None), commiter=commiter)

    assert result.response.delivery_enabled is True
    assert result.response.pickup_enabled is True
    assert result.response.default_city == "Москва"
    assert result.response.currency == "RUB"
    assert result.repository.created_default is True
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_delivery_settings_without_access_token_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_delivery_settings_customer_role_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_settings(role=UserRole.CUSTOMER)


@pytest.mark.asyncio
async def test_admin_delivery_settings_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_settings(role=UserRole.CONTENT_MANAGER)


@pytest.mark.asyncio
async def test_admin_delivery_settings_does_not_return_service_fields() -> None:
    result = await get_settings()

    dumped = result.response.model_dump()

    assert "id" not in dumped
    assert "created_date" not in dumped
    assert "internal_secret" not in dumped


@pytest.mark.asyncio
async def test_admin_delivery_settings_response_is_cached() -> None:
    result = await get_settings()

    assert "admin:delivery:settings" in result.redis_service.values
    assert result.redis_service.ttls["admin:delivery:settings"] == settings.admin_delivery.settings_cache_ttl_seconds
