from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.push_notifications import (
    broadcast_push,
    get_vapid_public_key,
    send_test_push,
    subscribe_push,
    unsubscribe_push,
)
from source.db.models.choises.enum import UserRole
from source.db.models.push_subscription import PushSubscription
from source.schemas.pydantic.push_subscription import (
    PushSubscriptionCreate,
    PushSubscriptionKeys,
    SendPushNotificationRequest,
)


def _unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_get_vapid_public_key():
    mock_service = MagicMock()
    mock_service.get_public_key.return_value = "test_vapid_public_key_123"

    response = await _unwrap(get_vapid_public_key)(web_push_service=mock_service)
    assert response.public_key == "test_vapid_public_key_123"


@pytest.mark.asyncio
async def test_subscribe_push_success():
    mock_session = AsyncMock()
    mock_commiter = AsyncMock()
    mock_repo = AsyncMock()

    now = datetime.now(timezone.utc)
    mock_subscription = PushSubscription(
        id=42,
        user_id=1,
        endpoint="https://push.example.com/sub/abc",
        p256dh="key1",
        auth="key2",
        is_active=True,
        created_date=now,
        updated_date=now,
    )
    mock_repo.save_or_update.return_value = mock_subscription

    payload = PushSubscriptionCreate(
        endpoint="https://push.example.com/sub/abc",
        keys=PushSubscriptionKeys(p256dh="key1", auth="key2"),
        user_agent="Mozilla/5.0",
    )
    user = SimpleNamespace(id=1, role=UserRole.CUSTOMER)

    response = await _unwrap(subscribe_push)(
        body=payload,
        current_user=user,
        session=mock_session,
        commiter=mock_commiter,
        push_subscription_repository=mock_repo,
    )

    assert response.id == 42
    assert response.endpoint == "https://push.example.com/sub/abc"
    assert response.is_active is True
    mock_commiter.commit.assert_called_once()


@pytest.mark.asyncio
async def test_unsubscribe_push_missing_endpoint():
    mock_session = AsyncMock()
    mock_commiter = AsyncMock()
    mock_repo = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await _unwrap(unsubscribe_push)(
            body={},
            session=mock_session,
            commiter=mock_commiter,
            push_subscription_repository=mock_repo,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_unsubscribe_push_success():
    mock_session = AsyncMock()
    mock_commiter = AsyncMock()
    mock_repo = AsyncMock()

    res = await _unwrap(unsubscribe_push)(
        body={"endpoint": "https://push.example.com/sub/abc"},
        session=mock_session,
        commiter=mock_commiter,
        push_subscription_repository=mock_repo,
    )
    assert res["success"] is True
    mock_repo.deactivate.assert_called_once_with(
        session=mock_session,
        endpoint="https://push.example.com/sub/abc",
    )
    mock_commiter.commit.assert_called_once()


@pytest.mark.asyncio
async def test_send_test_push_unauthorized():
    mock_session = AsyncMock()
    mock_commiter = AsyncMock()
    mock_repo = AsyncMock()
    mock_service = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await _unwrap(send_test_push)(
            body=SendPushNotificationRequest(title="Test", body="Body"),
            current_user=None,
            session=mock_session,
            commiter=mock_commiter,
            push_subscription_repository=mock_repo,
            web_push_service=mock_service,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_broadcast_push_success():
    mock_session = AsyncMock()
    mock_commiter = AsyncMock()
    mock_repo = AsyncMock()
    mock_service = AsyncMock()
    mock_service.broadcast.return_value = (5, 0)

    admin = SimpleNamespace(id=99, role=UserRole.ADMIN)
    response = await _unwrap(broadcast_push)(
        body=SendPushNotificationRequest(title="Акция", body="Скидка 20%"),
        current_user=admin,
        session=mock_session,
        commiter=mock_commiter,
        push_subscription_repository=mock_repo,
        web_push_service=mock_service,
    )

    assert response.success is True
    assert response.sent_count == 5
    assert response.failed_count == 0
    mock_commiter.commit.assert_called_once()
