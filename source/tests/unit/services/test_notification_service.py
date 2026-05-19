from datetime import datetime
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import InactiveUserError
from source.errors.notification import (
    NotificationAccessDeniedError,
    NotificationEmailDisabledError,
    NotificationNotFoundError,
    NotificationTelegramChatIdMissingError,
    NotificationTelegramDisabledError,
)
from source.schemas.pydantic.notifications import (
    NotificationListResponse,
    NotificationQueryParams,
    NotificationResponse,
    TestEmailRequest,
    TestTelegramRequest,
)
from source.services.notification_cache import NotificationCacheService
from source.services.notifications import NotificationService
from source.utils.query_hash import build_query_hash


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted_patterns = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)
        prefix = pattern.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                del self.values[key]


class FakeNotificationRepository:
    def __init__(self, notifications=None) -> None:
        self.notifications = notifications if notifications is not None else [
            build_notification(notification_id=1, user_id=1, type="order_status", is_read=False, created_at=datetime(2026, 5, 12, 10)),
            build_notification(notification_id=2, user_id=1, type="payment", is_read=True, created_at=datetime(2026, 5, 12, 9)),
            build_notification(notification_id=3, user_id=2, type="order_status", is_read=False, created_at=datetime(2026, 5, 12, 11)),
        ]
        self.requested_user_id = None

    async def get_by_user_id(self, *, session, user_id: int, query: NotificationQueryParams):
        self.requested_user_id = user_id
        notifications = self._filter(user_id=user_id, query=query)
        notifications.sort(key=lambda notification: notification.created_date, reverse=True)
        return [self._build_response(notification) for notification in notifications[query.offset : query.offset + query.limit]]

    async def count_by_user_id(self, *, session, user_id: int, query: NotificationQueryParams | None = None):
        return len(self._filter(user_id=user_id, query=query))

    async def count_unread_by_user_id(self, *, session, user_id: int):
        return len([notification for notification in self.notifications if notification.user_id == user_id and not notification.is_read])

    async def get_by_id(self, *, session, notification_id: int):
        return next((notification for notification in self.notifications if notification.id == notification_id), None)

    async def mark_as_read(self, *, session, notification):
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime(2026, 5, 12, 11)
        return notification

    def _filter(self, *, user_id: int, query: NotificationQueryParams | None):
        notifications = [notification for notification in self.notifications if notification.user_id == user_id]
        if query is None:
            return notifications
        if query.unread_only:
            notifications = [notification for notification in notifications if not notification.is_read]
        if query.type is not None:
            notifications = [notification for notification in notifications if notification.type == query.type]
        return notifications

    def _build_response(self, notification) -> NotificationResponse:
        return NotificationResponse(
            id=notification.id,
            type=notification.type,
            title=notification.title,
            message=notification.message,
            is_read=notification.is_read,
            read_at=notification.read_at,
            created_at=notification.created_date,
        )


class FakeNotificationLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)


class FakeEmailService:
    def __init__(self, *, fail=None) -> None:
        self.fail = fail
        self.sent = []

    async def send_email(self, *, email: str, subject: str, message: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append({"email": email, "subject": subject, "message": message})


class FakeTelegramService:
    def __init__(self, *, fail=None) -> None:
        self.fail = fail
        self.sent = []

    async def send_message(self, *, chat_id: str, message: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append({"chat_id": chat_id, "message": message})


def build_user(*, user_id: int = 1, role=UserRole.CUSTOMER, is_active: bool = True):
    return SimpleNamespace(id=user_id, role=role, is_active=is_active, is_deleted=False)


def build_notification(
    *,
    notification_id: int,
    user_id: int,
    type: str,
    is_read: bool,
    created_at: datetime,
):
    return SimpleNamespace(
        id=notification_id,
        user_id=user_id,
        type=type,
        title="Заказ собирается",
        message="Ваш заказ ORD-000101 передан в сборку",
        is_read=is_read,
        read_at=datetime(2026, 5, 12, 11) if is_read else None,
        created_date=created_at,
    )


async def get_notifications(*, repository=None, redis_service=None, query=None, user=None):
    return await NotificationService().get_user_notifications(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        query=query or NotificationQueryParams(),
        notification_repository=repository or FakeNotificationRepository(),
        notification_cache_service=NotificationCacheService(),
    )


@pytest.mark.asyncio
async def test_get_user_notifications_success() -> None:
    repository = FakeNotificationRepository()
    response = await get_notifications(repository=repository)

    assert response.total == 2
    assert response.unread_count == 1
    assert [item.id for item in response.items] == [1, 2]
    assert repository.requested_user_id == 1


@pytest.mark.asyncio
async def test_get_user_notifications_unread_only() -> None:
    response = await get_notifications(query=NotificationQueryParams(unread_only=True))

    assert response.total == 1
    assert all(not item.is_read for item in response.items)


@pytest.mark.asyncio
async def test_get_user_notifications_type_filter() -> None:
    response = await get_notifications(query=NotificationQueryParams(type="payment"))

    assert response.total == 1
    assert response.items[0].type == "payment"


@pytest.mark.asyncio
async def test_get_user_notifications_pagination() -> None:
    response = await get_notifications(query=NotificationQueryParams(page=2, limit=1))

    assert response.total == 2
    assert response.pages == 2
    assert response.items[0].id == 2


@pytest.mark.asyncio
async def test_get_user_notifications_returns_only_current_user_notifications() -> None:
    response = await get_notifications(user=build_user(user_id=2))

    assert response.total == 1
    assert response.items[0].id == 3


@pytest.mark.asyncio
async def test_get_user_notifications_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    query = NotificationQueryParams(type="payment")
    query_hash = build_query_hash(query.model_dump())
    cached_response = NotificationListResponse(
        items=[
            NotificationResponse(
                id=10,
                type="payment",
                title="Оплата",
                message="Оплата получена",
                is_read=False,
                created_at=datetime(2026, 5, 12, 10),
            ),
        ],
        total=1,
        unread_count=1,
        page=1,
        limit=20,
        pages=1,
    )
    redis_service.values[f"notifications:1:{query_hash}"] = cached_response.model_dump_json()

    response = await get_notifications(redis_service=redis_service, query=query)

    assert response == cached_response


@pytest.mark.asyncio
async def test_get_user_notifications_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = NotificationQueryParams(unread_only=True)
    query_hash = build_query_hash(query.model_dump())

    await get_notifications(redis_service=redis_service, query=query)

    cache_key = f"notifications:1:{query_hash}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.notifications.cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_user_notifications_inactive_user_error() -> None:
    with pytest.raises(InactiveUserError):
        await get_notifications(user=build_user(is_active=False))


@pytest.mark.asyncio
async def test_mark_as_read_success() -> None:
    repository = FakeNotificationRepository()
    redis_service = FakeRedisService()
    redis_service.values["notifications:1:test"] = "{}"

    response = await NotificationService().mark_as_read(
        session=None,
        redis_service=redis_service,
        user=build_user(),
        notification_id=1,
        notification_repository=repository,
        notification_cache_service=NotificationCacheService(),
    )

    assert response.is_read is True
    assert response.read_at == datetime(2026, 5, 12, 11)
    assert redis_service.deleted_patterns == ["notifications:1:*"]


@pytest.mark.asyncio
async def test_mark_as_read_already_read_success() -> None:
    repository = FakeNotificationRepository()

    response = await NotificationService().mark_as_read(
        session=None,
        redis_service=FakeRedisService(),
        user=build_user(),
        notification_id=2,
        notification_repository=repository,
        notification_cache_service=NotificationCacheService(),
    )

    assert response.is_read is True


@pytest.mark.asyncio
async def test_mark_as_read_foreign_notification_error() -> None:
    with pytest.raises(NotificationAccessDeniedError):
        await NotificationService().mark_as_read(
            session=None,
            redis_service=FakeRedisService(),
            user=build_user(),
            notification_id=3,
            notification_repository=FakeNotificationRepository(),
            notification_cache_service=NotificationCacheService(),
        )


@pytest.mark.asyncio
async def test_mark_as_read_not_found_error() -> None:
    with pytest.raises(NotificationNotFoundError):
        await NotificationService().mark_as_read(
            session=None,
            redis_service=FakeRedisService(),
            user=build_user(),
            notification_id=999,
            notification_repository=FakeNotificationRepository(),
            notification_cache_service=NotificationCacheService(),
        )


@pytest.mark.asyncio
async def test_send_test_email_success_logs_attempt() -> None:
    email_service = FakeEmailService()
    log_repository = FakeNotificationLogRepository()

    response = await NotificationService().send_test_email(
        session=None,
        user=build_user(role=UserRole.ADMIN),
        data=TestEmailRequest(email="admin@example.com", subject="Тест", message="Проверка"),
        email_service=email_service,
        notification_log_repository=log_repository,
    )

    assert response.email == "admin@example.com"
    assert email_service.sent[0]["email"] == "admin@example.com"
    assert log_repository.logs[0]["status"] == "sent"


@pytest.mark.asyncio
async def test_send_test_email_disabled_logs_attempt() -> None:
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationEmailDisabledError):
        await NotificationService().send_test_email(
            session=None,
            user=build_user(role=UserRole.ADMIN),
            data=TestEmailRequest(email="admin@example.com"),
            email_service=FakeEmailService(fail=NotificationEmailDisabledError()),
            notification_log_repository=log_repository,
        )

    assert log_repository.logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_send_test_telegram_success_to_chat_id_logs_attempt() -> None:
    telegram_service = FakeTelegramService()
    log_repository = FakeNotificationLogRepository()

    response = await NotificationService().send_test_telegram(
        session=None,
        user=build_user(role=UserRole.ADMIN),
        data=TestTelegramRequest(chat_id="123456789", message="Проверка"),
        telegram_service=telegram_service,
        notification_log_repository=log_repository,
    )

    assert response.chat_id == "123456789"
    assert telegram_service.sent[0]["chat_id"] == "123456789"
    assert log_repository.logs[0]["status"] == "sent"


@pytest.mark.asyncio
async def test_send_test_telegram_uses_admin_chat_id_from_env(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "admin_chat_id", "987654321")
    telegram_service = FakeTelegramService()

    response = await NotificationService().send_test_telegram(
        session=None,
        user=build_user(role=UserRole.ADMIN),
        data=TestTelegramRequest(),
        telegram_service=telegram_service,
        notification_log_repository=FakeNotificationLogRepository(),
    )

    assert response.chat_id == "987654321"
    assert telegram_service.sent[0]["chat_id"] == "987654321"


@pytest.mark.asyncio
async def test_send_test_telegram_chat_id_missing_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.telegram, "admin_chat_id", "")

    with pytest.raises(NotificationTelegramChatIdMissingError):
        await NotificationService().send_test_telegram(
            session=None,
            user=build_user(role=UserRole.ADMIN),
            data=TestTelegramRequest(),
            telegram_service=FakeTelegramService(),
            notification_log_repository=FakeNotificationLogRepository(),
        )


@pytest.mark.asyncio
async def test_send_test_telegram_disabled_logs_attempt() -> None:
    log_repository = FakeNotificationLogRepository()

    with pytest.raises(NotificationTelegramDisabledError):
        await NotificationService().send_test_telegram(
            session=None,
            user=build_user(role=UserRole.ADMIN),
            data=TestTelegramRequest(chat_id="123456789"),
            telegram_service=FakeTelegramService(fail=NotificationTelegramDisabledError()),
            notification_log_repository=log_repository,
        )

    assert log_repository.logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_send_test_telegram_response_does_not_return_bot_token() -> None:
    response = await NotificationService().send_test_telegram(
        session=None,
        user=build_user(role=UserRole.ADMIN),
        data=TestTelegramRequest(chat_id="123456789"),
        telegram_service=FakeTelegramService(),
        notification_log_repository=FakeNotificationLogRepository(),
    )

    assert "bot_token" not in response.model_dump()
