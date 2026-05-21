from datetime import datetime
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.schemas.pydantic.notifications import AdminNotificationSettingsResponse
from source.services.admin_auth import PermissionService
from source.services.admin_notification import AdminNotificationService
from source.services.notification_settings_cache import NotificationSettingsCacheService


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


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class FakeNotificationSettingsRepository:
    def __init__(self, notification_settings=None, created: bool = False) -> None:
        self.notification_settings = notification_settings
        self.created = created
        self.called = False

    async def get_or_create_default(self, *, session):
        self.called = True
        if self.notification_settings is None:
            self.notification_settings = build_notification_settings()
        return self.notification_settings, self.created


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
        is_deleted=False,
        is_blocked=False,
    )


def build_notification_settings(**kwargs):
    defaults = {
        "email_enabled": True,
        "email_from": "noreply@example.com",
        "email_sender_name": "Супермаркет",
        "telegram_enabled": True,
        "telegram_admin_chat_id": "123456789",
        "notify_admin_new_order": True,
        "notify_admin_payment_error": True,
        "notify_admin_1c_error": True,
        "notify_customer_order_created": True,
        "notify_customer_order_status": True,
        "notify_customer_payment": True,
        "notify_customer_delivery": True,
        "updated_date": datetime(2026, 5, 12, 10, 0, tzinfo=settings.tz),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


async def get_settings(*, redis_service=None, repository=None, user=None, commiter=None):
    return await AdminNotificationService().get_settings(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        notification_settings_repository=repository or FakeNotificationSettingsRepository(),
        notification_settings_cache_service=NotificationSettingsCacheService(),
    )


@pytest.mark.asyncio
async def test_admin_notification_settings_success() -> None:
    response = await get_settings(repository=FakeNotificationSettingsRepository(build_notification_settings()))

    assert response.email_from == "noreply@example.com"
    assert response.email_sender_name == "Супермаркет"
    assert response.telegram_admin_chat_id == "123456789"
    assert response.notify_admin_new_order is True


@pytest.mark.asyncio
async def test_admin_notification_settings_from_redis() -> None:
    redis_service = FakeRedisService()
    cached = AdminNotificationSettingsResponse(
        email_enabled=False,
        email_from="cached@example.com",
        email_sender_name="Cached",
        telegram_enabled=False,
        telegram_admin_chat_id="42",
        notify_admin_new_order=True,
        notify_admin_payment_error=True,
        notify_admin_1c_error=True,
        notify_customer_order_created=True,
        notify_customer_order_status=True,
        notify_customer_payment=True,
        notify_customer_delivery=True,
        updated_at=datetime(2026, 5, 12, 10, 0, tzinfo=settings.tz),
    )
    redis_service.values["admin:notifications:settings"] = cached.model_dump_json()
    repository = FakeNotificationSettingsRepository()

    response = await get_settings(redis_service=redis_service, repository=repository)

    assert response == cached
    assert repository.called is False


@pytest.mark.asyncio
async def test_admin_notification_settings_default_created_and_cached() -> None:
    redis_service = FakeRedisService()
    commiter = FakeCommiter()

    response = await get_settings(
        redis_service=redis_service,
        repository=FakeNotificationSettingsRepository(notification_settings=None, created=True),
        commiter=commiter,
    )

    assert response.email_sender_name == "Супермаркет"
    assert commiter.committed is True
    assert redis_service.ttls["admin:notifications:settings"] == 600


@pytest.mark.asyncio
async def test_admin_notification_settings_does_not_return_email_password() -> None:
    response = await get_settings(repository=FakeNotificationSettingsRepository(build_notification_settings()))

    assert "EMAIL_PASSWORD" not in response.model_dump_json()
    assert "password" not in response.model_dump()


@pytest.mark.asyncio
async def test_admin_notification_settings_does_not_return_telegram_bot_token() -> None:
    response = await get_settings(repository=FakeNotificationSettingsRepository(build_notification_settings()))

    assert "TELEGRAM_BOT_TOKEN" not in response.model_dump_json()
    assert "bot_token" not in response.model_dump()


@pytest.mark.asyncio
async def test_admin_notification_settings_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_settings(
            user=build_user(role=UserRole.MANAGER),
            repository=FakeNotificationSettingsRepository(build_notification_settings()),
        )
