from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.loyalty import (
    connect_telegram,
    get_my_loyalty,
    get_my_referral,
    get_telegram_status,
)
from source.db.models.choises.enum import UserRole
from source.db.models.store_settings import StoreSettings
from source.db.models.user import User
from source.schemas.pydantic.loyalty import LoyaltyResponse
from source.schemas.pydantic.telegram import (
    TelegramConnectResponse,
    TelegramStatusResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=5, name="Покупатель", role=UserRole.CUSTOMER, is_active=True)


# ---------------------------------------------------------
# GET /profile/loyalty
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_my_loyalty_success(active_user):
    service = AsyncMock()
    service.get_loyalty_info.return_value = LoyaltyResponse(
        balance=150,
        level="Золотой",
        cashback_percent=5,
        transactions=[],
    )

    response = await unwrap(get_my_loyalty)(
        current_user=active_user,
        session=AsyncMock(),
        loyalty_repository=AsyncMock(),
        loyalty_service=service,
    )

    assert response.balance == 150
    assert response.level == "Золотой"
    assert response.cashback_percent == 5


# ---------------------------------------------------------
# POST /profile/telegram/connect
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_telegram_success(active_user):
    service = AsyncMock()
    service.create_connect_token.return_value = TelegramConnectResponse(
        connect_url="https://t.me/pobeda_bot?start=token123",
        token="token123",
        expires_in=600,
        is_connected=False,
    )

    response = await unwrap(connect_telegram)(
        current_user=active_user,
        redis_service=AsyncMock(),
        telegram_connect_service=service,
    )

    assert response.token == "token123"
    assert "t.me" in response.connect_url
    assert response.is_connected is False


# ---------------------------------------------------------
# GET /profile/telegram/status
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_telegram_status_success(active_user):
    service = AsyncMock()
    service.get_status.return_value = TelegramStatusResponse(
        is_connected=True,
        telegram_chat_id="123456789",
    )

    response = await unwrap(get_telegram_status)(
        current_user=active_user,
        telegram_connect_service=service,
    )

    assert response.is_connected is True
    assert response.telegram_chat_id == "123456789"


# ---------------------------------------------------------
# GET /profile/referral
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_my_referral_success(active_user):
    settings_repo = AsyncMock()
    store_settings = StoreSettings(referral_program_enabled=True)
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    response = await unwrap(get_my_referral)(
        current_user=active_user,
        session=AsyncMock(),
        settings_repository=settings_repo,
    )

    assert response.code.startswith("REF-")
    assert "/register?ref=" in response.link
    assert response.reward_amount == 500


@pytest.mark.asyncio
async def test_get_my_referral_disabled_forbidden(active_user):
    settings_repo = AsyncMock()
    store_settings = StoreSettings(referral_program_enabled=False)
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_my_referral)(
            current_user=active_user,
            session=AsyncMock(),
            settings_repository=settings_repo,
        )
    assert exc.value.status_code == 403
    assert "отключена" in exc.value.detail.lower()
