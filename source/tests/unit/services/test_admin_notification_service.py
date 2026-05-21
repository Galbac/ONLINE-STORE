from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.settings import EmptyNotificationSettingsUpdateError
from source.schemas.pydantic.notifications import AdminNotificationSettingsResponse, AdminNotificationSettingsUpdateRequest
from source.schemas.pydantic.notifications import AdminTestEmailRequest, AdminTestTelegramRequest
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_notification import AdminNotificationService
from source.services.notification_settings_cache import NotificationSettingsCacheService
from source.errors.notification import (
    NotificationEmailDisabledError,
    NotificationSendError,
    NotificationTelegramChatIdMissingError,
    NotificationTelegramDisabledError,
)


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
        self.updated_payload: dict | None = None

    async def get_or_create_default(self, *, session):
        self.called = True
        if self.notification_settings is None:
            self.notification_settings = build_notification_settings()
        return self.notification_settings, self.created

    async def update(self, *, session, notification_settings, data: dict):
        self.updated_payload = data
        for field, value in data.items():
            setattr(notification_settings, field, value)
        notification_settings.updated_date = datetime(2026, 5, 12, 11, 0, tzinfo=settings.tz)
        self.notification_settings = notification_settings
        return notification_settings


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.created_payload: dict | None = None

    async def create(self, *, session, **data):
        self.created_payload = data
        return SimpleNamespace(**data)


class FakeNotificationLogRepository:
    def __init__(self) -> None:
        self.logs: list[dict] = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)


class FakeEmailService:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.sent: list[dict] = []

    async def send_email(self, *, email: str, subject: str, message: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append({"email": email, "subject": subject, "message": message})


class FakeTelegramService:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.sent: list[dict] = []

    async def send_message(self, *, chat_id: str, message: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append({"chat_id": chat_id, "message": message})


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        email="admin@example.com",
        phone=None,
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


async def update_settings(
    *,
    data=None,
    redis_service=None,
    repository=None,
    user=None,
    commiter=None,
    audit_log_repository=None,
):
    return await AdminNotificationService().update_settings(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        data=data or AdminNotificationSettingsUpdateRequest(email_enabled=False),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        notification_settings_repository=repository or FakeNotificationSettingsRepository(build_notification_settings()),
        notification_settings_cache_service=NotificationSettingsCacheService(),
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


async def send_test_email(
    *,
    data=None,
    repository=None,
    user=None,
    commiter=None,
    email_service=None,
    notification_log_repository=None,
):
    return await AdminNotificationService().send_test_email(
        session=object(),
        user=user or build_user(),
        data=data or AdminTestEmailRequest(email="admin@example.com"),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        email_service=email_service or FakeEmailService(),
        notification_settings_repository=repository or FakeNotificationSettingsRepository(build_notification_settings(email_enabled=True)),
        notification_log_repository=notification_log_repository or FakeNotificationLogRepository(),
    )


async def send_test_telegram(
    *,
    data=None,
    repository=None,
    user=None,
    commiter=None,
    telegram_service=None,
    notification_log_repository=None,
):
    return await AdminNotificationService().send_test_telegram(
        session=object(),
        user=user or build_user(),
        data=data or AdminTestTelegramRequest(chat_id="123456789"),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        telegram_service=telegram_service or FakeTelegramService(),
        notification_settings_repository=repository or FakeNotificationSettingsRepository(build_notification_settings(telegram_enabled=True)),
        notification_log_repository=notification_log_repository or FakeNotificationLogRepository(),
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


@pytest.mark.asyncio
async def test_admin_notification_settings_update_email_enabled_success() -> None:
    repository = FakeNotificationSettingsRepository(build_notification_settings(email_enabled=True))

    response = await update_settings(
        data=AdminNotificationSettingsUpdateRequest(email_enabled=False),
        repository=repository,
    )

    assert response.email_enabled is False
    assert repository.updated_payload == {"email_enabled": False}


@pytest.mark.asyncio
async def test_admin_notification_settings_update_telegram_enabled_success() -> None:
    response = await update_settings(data=AdminNotificationSettingsUpdateRequest(telegram_enabled=False))

    assert response.telegram_enabled is False


@pytest.mark.asyncio
async def test_admin_notification_settings_update_telegram_admin_chat_id_success() -> None:
    response = await update_settings(data=AdminNotificationSettingsUpdateRequest(telegram_admin_chat_id="-100123456789"))

    assert response.telegram_admin_chat_id == "-100123456789"


@pytest.mark.asyncio
async def test_admin_notification_settings_update_empty_body_error() -> None:
    with pytest.raises(EmptyNotificationSettingsUpdateError):
        await update_settings(data=AdminNotificationSettingsUpdateRequest())


def test_admin_notification_settings_update_invalid_email_error() -> None:
    with pytest.raises(ValidationError):
        AdminNotificationSettingsUpdateRequest(email_from="not-an-email")


def test_admin_notification_settings_update_rejects_secrets() -> None:
    with pytest.raises(ValidationError):
        AdminNotificationSettingsUpdateRequest.model_validate({"EMAIL_PASSWORD": "secret"})
    with pytest.raises(ValidationError):
        AdminNotificationSettingsUpdateRequest.model_validate({"TELEGRAM_BOT_TOKEN": "secret"})
    with pytest.raises(ValidationError):
        AdminNotificationSettingsUpdateRequest.model_validate({"smtp_password": "secret"})


@pytest.mark.asyncio
async def test_admin_notification_settings_update_does_not_return_secrets() -> None:
    response = await update_settings(data=AdminNotificationSettingsUpdateRequest(email_from="new@example.com"))

    payload = response.model_dump()
    assert "password" not in payload
    assert "bot_token" not in payload
    assert "smtp_username" not in payload


@pytest.mark.asyncio
async def test_admin_notification_settings_update_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await update_settings(
        data=AdminNotificationSettingsUpdateRequest(email_enabled=False),
        redis_service=redis_service,
    )

    assert "admin:notifications:settings" in redis_service.deleted


@pytest.mark.asyncio
async def test_admin_notification_settings_update_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await update_settings(
        data=AdminNotificationSettingsUpdateRequest(email_enabled=False),
        audit_log_repository=audit_log_repository,
    )

    assert audit_log_repository.created_payload["event"] == "admin_notification_settings_update"
    assert audit_log_repository.created_payload["details"]["changes"]["email_enabled"] == {
        "old": "True",
        "new": "False",
    }


@pytest.mark.asyncio
async def test_admin_test_email_success(monkeypatch) -> None:
    monkeypatch.setattr(settings.email_notifications, "enabled", True)
    email_service = FakeEmailService()
    log_repository = FakeNotificationLogRepository()

    response = await send_test_email(
        data=AdminTestEmailRequest(email="admin@example.com", subject="Тестовое письмо", message="Проверка"),
        email_service=email_service,
        notification_log_repository=log_repository,
    )

    assert response.message == "Тестовое email-уведомление отправлено"
    assert response.email == "admin@example.com"
    assert email_service.sent[0] == {
        "email": "admin@example.com",
        "subject": "Тестовое письмо",
        "message": "Проверка",
    }
    assert log_repository.logs[0]["status"] == "success"


def test_admin_test_email_invalid_email_error() -> None:
    with pytest.raises(ValidationError):
        AdminTestEmailRequest(email="not-an-email")


@pytest.mark.asyncio
async def test_admin_test_email_env_disabled_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.email_notifications, "enabled", False)
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationEmailDisabledError):
        await send_test_email(notification_log_repository=log_repository)

    assert log_repository.logs[0]["status"] == "error"
    assert log_repository.logs[0]["error_message"] == "Email-уведомления отключены"


@pytest.mark.asyncio
async def test_admin_test_email_settings_disabled_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.email_notifications, "enabled", True)
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationEmailDisabledError):
        await send_test_email(
            repository=FakeNotificationSettingsRepository(build_notification_settings(email_enabled=False)),
            notification_log_repository=log_repository,
        )

    assert log_repository.logs[0]["status"] == "error"


@pytest.mark.asyncio
async def test_admin_test_email_without_permission_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.email_notifications, "enabled", True)

    with pytest.raises(AdminAuthAccessDeniedError):
        await send_test_email(user=build_user(role=UserRole.MANAGER))


@pytest.mark.asyncio
async def test_admin_test_email_error_log_created(monkeypatch) -> None:
    monkeypatch.setattr(settings.email_notifications, "enabled", True)
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationSendError):
        await send_test_email(
            email_service=FakeEmailService(fail=RuntimeError("smtp failed")),
            notification_log_repository=log_repository,
        )

    assert log_repository.logs[0]["status"] == "error"
    assert log_repository.logs[0]["error_message"] == "smtp failed"


def test_admin_test_email_rejects_secrets() -> None:
    with pytest.raises(ValidationError):
        AdminTestEmailRequest.model_validate({"email": "admin@example.com", "EMAIL_PASSWORD": "secret"})
    with pytest.raises(ValidationError):
        AdminTestEmailRequest.model_validate({"email": "admin@example.com", "smtp_password": "secret"})


@pytest.mark.asyncio
async def test_admin_test_email_response_does_not_return_smtp_password(monkeypatch) -> None:
    monkeypatch.setattr(settings.email_notifications, "enabled", True)

    response = await send_test_email()

    payload = response.model_dump()
    assert "password" not in payload
    assert "smtp" not in payload


@pytest.mark.asyncio
async def test_admin_test_telegram_success_to_body_chat_id(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    telegram_service = FakeTelegramService()
    log_repository = FakeNotificationLogRepository()

    response = await send_test_telegram(
        data=AdminTestTelegramRequest(chat_id="123456789", message="Проверка"),
        telegram_service=telegram_service,
        notification_log_repository=log_repository,
    )

    assert response.message == "Тестовое Telegram-уведомление отправлено"
    assert response.chat_id == "123456789"
    assert telegram_service.sent[0] == {"chat_id": "123456789", "message": "Проверка"}
    assert log_repository.logs[0]["status"] == "success"


@pytest.mark.asyncio
async def test_admin_test_telegram_success_to_settings_chat_id(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    telegram_service = FakeTelegramService()

    response = await send_test_telegram(
        data=AdminTestTelegramRequest(),
        repository=FakeNotificationSettingsRepository(build_notification_settings(telegram_admin_chat_id="-100123")),
        telegram_service=telegram_service,
    )

    assert response.chat_id == "-100123"
    assert telegram_service.sent[0]["chat_id"] == "-100123"


@pytest.mark.asyncio
async def test_admin_test_telegram_success_to_env_chat_id(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    monkeypatch.setattr(settings.telegram, "admin_chat_id", "987654321")
    telegram_service = FakeTelegramService()

    response = await send_test_telegram(
        data=AdminTestTelegramRequest(),
        repository=FakeNotificationSettingsRepository(build_notification_settings(telegram_admin_chat_id=None)),
        telegram_service=telegram_service,
    )

    assert response.chat_id == "987654321"
    assert telegram_service.sent[0]["chat_id"] == "987654321"


@pytest.mark.asyncio
async def test_admin_test_telegram_missing_chat_id_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "admin_chat_id", "")

    with pytest.raises(NotificationTelegramChatIdMissingError):
        await send_test_telegram(
            data=AdminTestTelegramRequest(),
            repository=FakeNotificationSettingsRepository(build_notification_settings(telegram_admin_chat_id=None)),
        )


@pytest.mark.asyncio
async def test_admin_test_telegram_env_disabled_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", False)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationTelegramDisabledError):
        await send_test_telegram(notification_log_repository=log_repository)

    assert log_repository.logs[0]["status"] == "error"
    assert log_repository.logs[0]["error_message"] == "Telegram-уведомления отключены"


@pytest.mark.asyncio
async def test_admin_test_telegram_settings_disabled_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationTelegramDisabledError):
        await send_test_telegram(
            repository=FakeNotificationSettingsRepository(build_notification_settings(telegram_enabled=False)),
            notification_log_repository=log_repository,
        )

    assert log_repository.logs[0]["status"] == "error"


@pytest.mark.asyncio
async def test_admin_test_telegram_without_permission_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")

    with pytest.raises(AdminAuthAccessDeniedError):
        await send_test_telegram(user=build_user(role=UserRole.MANAGER))


@pytest.mark.asyncio
async def test_admin_test_telegram_bot_token_not_returned_or_logged(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    log_repository = FakeNotificationLogRepository()

    response = await send_test_telegram(notification_log_repository=log_repository)

    assert "secret-token" not in response.model_dump_json()
    assert "secret-token" not in str(log_repository.logs)
    assert "bot_token" not in response.model_dump()


@pytest.mark.asyncio
async def test_admin_test_telegram_error_log_created(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "enabled", True)
    monkeypatch.setattr(settings.telegram, "bot_token", "secret-token")
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationSendError):
        await send_test_telegram(
            telegram_service=FakeTelegramService(fail=RuntimeError("telegram failed")),
            notification_log_repository=log_repository,
        )

    assert log_repository.logs[0]["status"] == "error"
    assert log_repository.logs[0]["error_message"] == "telegram failed"
