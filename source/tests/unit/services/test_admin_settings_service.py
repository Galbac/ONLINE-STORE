from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.settings import EmptyAdminSettingsUpdateError
from source.schemas.pydantic.settings import AdminSettingsResponse, AdminSettingsUpdateRequest
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_settings import AdminSettingsService
from source.services.delivery_cache import DeliveryCacheService
from source.services.settings_cache import SettingsCacheService


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
        self.values.pop(key, None)

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted.append(pattern)


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeSettingsRepository:
    def __init__(self, store_settings=None) -> None:
        self.store_settings = store_settings
        self.created_default = False
        self.get_or_create_calls = 0
        self.updated = []

    async def get_or_create_default(self, *, session):
        self.get_or_create_calls += 1
        if self.store_settings is not None:
            return self.store_settings, False
        self.created_default = True
        self.store_settings = build_store_settings()
        return self.store_settings, True

    async def update(self, *, session, store_settings, data: dict):
        self.updated.append(data)
        for field, value in data.items():
            setattr(store_settings, field, value)
        store_settings.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return store_settings


class FakeDeliverySettingsRepository:
    def __init__(self, delivery_settings=None) -> None:
        self.delivery_settings = delivery_settings
        self.created_default = False
        self.get_or_create_calls = 0
        self.updated = []

    async def get_or_create_default(self, *, session):
        self.get_or_create_calls += 1
        if self.delivery_settings is not None:
            return self.delivery_settings, False
        self.created_default = True
        self.delivery_settings = build_delivery_settings()
        return self.delivery_settings, True

    async def update(self, *, session, delivery_settings, data: dict):
        self.updated.append(data)
        for field, value in data.items():
            setattr(delivery_settings, field, value)
        delivery_settings.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return delivery_settings


class FakeCartCacheService:
    async def invalidate_all_summaries(self, *, redis_service) -> None:
        await redis_service.delete_by_pattern("cart:summary:*")


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(**data)


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
        is_deleted=False,
        is_blocked=False,
    )


def build_store_settings():
    return SimpleNamespace(
        shop_name="Супермаркет",
        phone="+79990000000",
        email="info@example.com",
        address="Москва, ул. Тверская, 10",
        working_hours="Пн-Вс 09:00-22:00",
        online_payment_enabled=True,
        pay_on_delivery_enabled=True,
        maintenance_mode=False,
        smtp_password="secret",
        telegram_bot_token="secret",
        payment_secret_key="secret",
        updated_date=datetime(2026, 5, 12, 10, 0, 0),
    )


def build_delivery_settings():
    return SimpleNamespace(
        default_city="Москва",
        currency="RUB",
        delivery_enabled=True,
        pickup_enabled=True,
        min_order_amount=Decimal("1000.00"),
        updated_date=datetime(2026, 5, 12, 9, 0, 0),
    )


async def get_settings(
    *,
    redis_service=None,
    role=UserRole.ADMIN,
    settings_repository=None,
    delivery_settings_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    commiter = commiter or FakeCommiter()
    settings_repository = settings_repository or FakeSettingsRepository(build_store_settings())
    delivery_settings_repository = delivery_settings_repository or FakeDeliverySettingsRepository(build_delivery_settings())
    response = await AdminSettingsService().get_settings(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        commiter=commiter,
        permission_service=PermissionService(),
        settings_repository=settings_repository,
        delivery_settings_repository=delivery_settings_repository,
        settings_cache_service=SettingsCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        settings_repository=settings_repository,
        delivery_settings_repository=delivery_settings_repository,
        commiter=commiter,
    )


async def update_settings(
    *,
    data: AdminSettingsUpdateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    settings_repository=None,
    delivery_settings_repository=None,
    commiter=None,
    audit_log_repository=None,
):
    redis_service = redis_service or FakeRedisService()
    commiter = commiter or FakeCommiter()
    settings_repository = settings_repository or FakeSettingsRepository(build_store_settings())
    delivery_settings_repository = delivery_settings_repository or FakeDeliverySettingsRepository(build_delivery_settings())
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    response = await AdminSettingsService().update_settings(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        data=data or AdminSettingsUpdateRequest(shop_name=" Новый магазин "),
        commiter=commiter,
        permission_service=PermissionService(),
        settings_repository=settings_repository,
        delivery_settings_repository=delivery_settings_repository,
        settings_cache_service=SettingsCacheService(),
        delivery_cache_service=DeliveryCacheService(),
        cart_cache_service=FakeCartCacheService(),
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        settings_repository=settings_repository,
        delivery_settings_repository=delivery_settings_repository,
        commiter=commiter,
        audit_log_repository=audit_log_repository,
    )


@pytest.mark.asyncio
async def test_admin_settings_from_postgres_success() -> None:
    result = await get_settings()

    assert result.response.shop_name == "Супермаркет"
    assert result.response.phone == "+79990000000"
    assert result.response.email == "info@example.com"
    assert result.response.address == "Москва, ул. Тверская, 10"
    assert result.response.working_hours == "Пн-Вс 09:00-22:00"
    assert result.response.default_city == "Москва"
    assert result.response.currency == "RUB"
    assert result.response.delivery_enabled is True
    assert result.response.pickup_enabled is True
    assert result.response.online_payment_enabled is True
    assert result.response.pay_on_delivery_enabled is True
    assert result.response.min_order_amount == Decimal("1000.00")
    assert result.response.maintenance_mode is False
    assert result.response.updated_at == datetime(2026, 5, 12, 10, 0, 0)
    assert result.redis_service.ttls["admin:settings"] == settings.admin_settings.cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_settings_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminSettingsResponse(
        shop_name="Из кеша",
        phone="+79990000001",
        email="cache@example.com",
        address="Москва",
        working_hours="24/7",
        default_city="Казань",
        currency="RUB",
        delivery_enabled=False,
        pickup_enabled=True,
        online_payment_enabled=False,
        pay_on_delivery_enabled=True,
        min_order_amount=Decimal("500.00"),
        maintenance_mode=True,
        updated_at=datetime(2026, 5, 12, 10, 0, 0),
    )
    redis_service.values["admin:settings"] = cached_response.model_dump_json()
    settings_repository = FakeSettingsRepository(build_store_settings())

    result = await get_settings(redis_service=redis_service, settings_repository=settings_repository)

    assert result.response == cached_response
    assert settings_repository.get_or_create_calls == 0


@pytest.mark.asyncio
async def test_admin_settings_default_values_when_missing() -> None:
    commiter = FakeCommiter()
    result = await get_settings(
        settings_repository=FakeSettingsRepository(None),
        delivery_settings_repository=FakeDeliverySettingsRepository(None),
        commiter=commiter,
    )

    assert result.response.shop_name == "Супермаркет"
    assert result.response.default_city == "Москва"
    assert result.settings_repository.created_default is True
    assert result.delivery_settings_repository.created_default is True
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_settings_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_settings(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_settings_does_not_return_secrets() -> None:
    result = await get_settings()

    dumped = result.response.model_dump()

    assert "smtp_password" not in dumped
    assert "telegram_bot_token" not in dumped
    assert "payment_secret_key" not in dumped


@pytest.mark.asyncio
async def test_admin_settings_update_shop_name_success() -> None:
    result = await update_settings(data=AdminSettingsUpdateRequest(shop_name=" Новый магазин "))

    assert result.response.shop_name == "Новый магазин"
    assert result.settings_repository.updated[0] == {"shop_name": "Новый магазин"}
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_settings_update_phone_success() -> None:
    result = await update_settings(data=AdminSettingsUpdateRequest(phone=" +79990000002 "))

    assert result.response.phone == "+79990000002"
    assert result.settings_repository.updated[0] == {"phone": "+79990000002"}


@pytest.mark.asyncio
async def test_admin_settings_update_email_success() -> None:
    result = await update_settings(data=AdminSettingsUpdateRequest(email=" INFO@EXAMPLE.COM "))

    assert result.response.email == "info@example.com"
    assert result.settings_repository.updated[0] == {"email": "info@example.com"}


@pytest.mark.asyncio
async def test_admin_settings_update_empty_body_error() -> None:
    with pytest.raises(EmptyAdminSettingsUpdateError):
        await update_settings(data=AdminSettingsUpdateRequest())


def test_admin_settings_update_invalid_email_error() -> None:
    with pytest.raises(ValidationError):
        AdminSettingsUpdateRequest(email="bad-email")


def test_admin_settings_update_invalid_phone_error() -> None:
    with pytest.raises(ValidationError, match="Неверный формат телефона"):
        AdminSettingsUpdateRequest(phone="phone")


def test_admin_settings_update_negative_min_order_amount_error() -> None:
    with pytest.raises(ValidationError, match="min_order_amount"):
        AdminSettingsUpdateRequest(min_order_amount=Decimal("-1.00"))


@pytest.mark.asyncio
async def test_admin_settings_update_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await update_settings(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_settings_update_invalidates_cache() -> None:
    result = await update_settings()

    assert "admin:settings" in result.redis_service.deleted
    assert "public:settings" in result.redis_service.deleted
    assert "delivery:options" in result.redis_service.deleted
    assert "cart:summary:*" in result.redis_service.deleted


@pytest.mark.asyncio
async def test_admin_settings_update_audit_log_created() -> None:
    result = await update_settings(data=AdminSettingsUpdateRequest(shop_name="Новый магазин"))

    assert result.audit_log_repository.logs[0]["event"] == "admin_settings_update"
    assert result.audit_log_repository.logs[0]["user_id"] == 1
    assert result.audit_log_repository.logs[0]["ip_address"] == "127.0.0.1"
    assert result.audit_log_repository.logs[0]["user_agent"] == "pytest"
    assert result.audit_log_repository.logs[0]["details"]["actor_id"] == 1
    assert result.audit_log_repository.logs[0]["details"]["changes"]["shop_name"] == {
        "old": "Супермаркет",
        "new": "Новый магазин",
    }
