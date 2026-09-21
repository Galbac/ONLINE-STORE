import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from pywebpush import WebPushException

from source.config.settings import settings
from source.db.models.push_subscription import PushSubscription
from source.services.web_push import WebPushService


class FakePushSubscriptionRepository:
    def __init__(self, subscriptions=None):
        self.subscriptions = subscriptions or []
        self.deactivated = []

    async def get_active_by_user_id(self, *, session, user_id):
        return [s for s in self.subscriptions if s.user_id == user_id and s.is_active]

    async def get_all_active(self, *, session):
        return [s for s in self.subscriptions if s.is_active]

    async def deactivate(self, *, session, endpoint):
        self.deactivated.append(endpoint)
        for s in self.subscriptions:
            if s.endpoint == endpoint:
                s.is_active = False


@pytest.mark.asyncio
async def test_web_push_service_get_public_key():
    service = WebPushService()
    key = service.get_public_key()
    assert key == settings.web_push.vapid_public_key
    assert len(key) > 20


@pytest.mark.asyncio
async def test_web_push_service_send_to_subscription_success():
    service = WebPushService()
    sub = PushSubscription(
        id=1,
        user_id=10,
        endpoint="https://push.example.com/sub/123",
        p256dh="key_p256dh_test",
        auth="key_auth_test",
        is_active=True,
    )
    repo = FakePushSubscriptionRepository([sub])
    mock_session = MagicMock()

    with patch.object(service, "_send_webpush_sync") as mock_send:
        mock_send.return_value = None
        result = await service.send_to_subscription(
            session=mock_session,
            push_subscription_repository=repo,
            subscription=sub,
            title="Заказ оформлен",
            body="Ваш заказ №1001 принят",
            url="/profile/orders/1001",
        )
        assert result is True
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_web_push_service_handles_410_gone_and_deactivates():
    service = WebPushService()
    sub = PushSubscription(
        id=1,
        user_id=10,
        endpoint="https://push.example.com/sub/expired",
        p256dh="key_p256dh_test",
        auth="key_auth_test",
        is_active=True,
    )
    repo = FakePushSubscriptionRepository([sub])
    mock_session = MagicMock()

    fake_response = SimpleNamespace(status_code=410)
    exception = WebPushException("Push subscription has expired", response=fake_response)

    with patch.object(service, "_send_webpush_sync", side_effect=exception):
        result = await service.send_to_subscription(
            session=mock_session,
            push_subscription_repository=repo,
            subscription=sub,
            title="Тест",
            body="Сообщение",
        )
        assert result is False
        assert sub.endpoint in repo.deactivated
        assert sub.is_active is False


@pytest.mark.asyncio
async def test_web_push_service_send_to_user():
    service = WebPushService()
    sub1 = PushSubscription(
        id=1,
        user_id=5,
        endpoint="https://push.example.com/sub/1",
        p256dh="k1",
        auth="a1",
        is_active=True,
    )
    sub2 = PushSubscription(
        id=2,
        user_id=5,
        endpoint="https://push.example.com/sub/2",
        p256dh="k2",
        auth="a2",
        is_active=True,
    )
    repo = FakePushSubscriptionRepository([sub1, sub2])
    mock_session = MagicMock()

    with patch.object(service, "_send_webpush_sync", return_value=None):
        sent = await service.send_to_user(
            session=mock_session,
            push_subscription_repository=repo,
            user_id=5,
            title="Курьер в пути",
            body="Курьер будет через 15 минут",
            url="/profile/orders/50",
        )
        assert sent == 2
