from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from source.api.api_v1.views.public_settings import get_public_store_settings
from source.db.models.store_settings import StoreSettings
from source.schemas.pydantic.public_settings import PublicStoreSettingsResponse


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_get_public_store_settings_success() -> None:
    session = AsyncMock()
    settings_repo = AsyncMock()

    store_settings = StoreSettings(
        shop_name="Супермаркет Победа",
        legal_name="ИП Победа",
        inn="054701234567",
        ogrn="326050000123456",
        phone="+7 (928) 519-14-85",
        email="info@pobeda.local",
        address="ул. Победы, 87А",
        working_hours="Круглосуточно",
        online_payment_enabled=True,
        pay_on_delivery_enabled=True,
        maintenance_mode=False,
        promo_codes_enabled=True,
        referral_program_enabled=True,
        loyalty_program_enabled=True,
        privacy_policy_url="/privacy",
        user_agreement_url="/offer",
        personal_data_consent_url="/personal-data-consent",
    )
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    response = await unwrap(get_public_store_settings)(
        session=session,
        settings_repository=settings_repo,
    )

    assert isinstance(response, PublicStoreSettingsResponse)
    assert response.shop_name == "Супермаркет Победа"
    assert response.legal_name == "ИП Победа"
    assert response.privacy_policy_url == "/privacy"
    assert response.user_agreement_url == "/offer"
    assert response.personal_data_consent_url == "/personal-data-consent"
    assert response.online_payment_enabled is True
    assert response.maintenance_mode is False


@pytest.mark.asyncio
async def test_get_public_store_settings_custom_legal_urls() -> None:
    session = AsyncMock()
    settings_repo = AsyncMock()

    store_settings = StoreSettings(
        shop_name="Победа",
        online_payment_enabled=True,
        pay_on_delivery_enabled=True,
        maintenance_mode=False,
        promo_codes_enabled=True,
        referral_program_enabled=True,
        loyalty_program_enabled=True,
        privacy_policy_url="https://legal.example.com/privacy",
        user_agreement_url="https://legal.example.com/terms",
        personal_data_consent_url="https://legal.example.com/consent",
    )
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    response = await unwrap(get_public_store_settings)(
        session=session,
        settings_repository=settings_repo,
    )

    assert response.privacy_policy_url == "https://legal.example.com/privacy"
    assert response.user_agreement_url == "https://legal.example.com/terms"
    assert response.personal_data_consent_url == "https://legal.example.com/consent"


@pytest.mark.asyncio
async def test_get_public_store_settings_with_schedule() -> None:
    session = AsyncMock()
    settings_repo = AsyncMock()

    custom_schedule = [
        {"day": 1, "day_name": "Понедельник", "is_day_off": False, "open_time": "08:00", "close_time": "22:00"},
        {"day": 2, "day_name": "Вторник", "is_day_off": False, "open_time": "08:00", "close_time": "22:00"},
        {"day": 3, "day_name": "Среда", "is_day_off": False, "open_time": "08:00", "close_time": "22:00"},
        {"day": 4, "day_name": "Четверг", "is_day_off": False, "open_time": "08:00", "close_time": "22:00"},
        {"day": 5, "day_name": "Пятница", "is_day_off": False, "open_time": "08:00", "close_time": "22:00"},
        {"day": 6, "day_name": "Суббота", "is_day_off": False, "open_time": "09:00", "close_time": "20:00"},
        {"day": 7, "day_name": "Воскресенье", "is_day_off": True, "open_time": None, "close_time": None},
    ]

    store_settings = StoreSettings(
        shop_name="Победа",
        schedule=custom_schedule,
        maintenance_mode=False,
    )
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    response = await unwrap(get_public_store_settings)(
        session=session,
        settings_repository=settings_repo,
    )

    assert response.schedule is not None
    assert len(response.schedule) == 7
    assert response.schedule[0].day == 1
    assert response.schedule[6].day == 7
    assert response.schedule[6].is_day_off is True
    assert isinstance(response.is_open_now, bool)
    assert response.current_status_text is not None
