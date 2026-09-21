from datetime import datetime, UTC
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from source.db.models.choises.enum import UserRole
from source.db.models.store_settings import StoreSettings
from source.db.models.user import User
from source.schemas.pydantic.settings import (
    AdminSettingsResponse,
    AdminSettingsUpdateRequest,
)
from source.services.admin_settings import AdminSettingsService


# ---------------------------------------------------------
# 1. Валидация AdminSettingsUpdateRequest
# ---------------------------------------------------------

def test_admin_settings_update_legal_urls_valid():
    req = AdminSettingsUpdateRequest(
        privacy_policy_url="/custom-privacy",
        user_agreement_url="/custom-offer",
        personal_data_consent_url="/custom-consent",
    )
    assert req.privacy_policy_url == "/custom-privacy"
    assert req.user_agreement_url == "/custom-offer"
    assert req.personal_data_consent_url == "/custom-consent"


def test_admin_settings_update_legal_urls_stripping():
    req = AdminSettingsUpdateRequest(
        privacy_policy_url="   /privacy   ",
        user_agreement_url="   ",  # пустая строка нормализуется в None
    )
    assert req.privacy_policy_url == "/privacy"
    assert req.user_agreement_url is None


def test_admin_settings_update_legal_urls_max_length():
    with pytest.raises(ValidationError):
        AdminSettingsUpdateRequest(privacy_policy_url="a" * 501)


# ---------------------------------------------------------
# 2. Сериализация AdminSettingsResponse
# ---------------------------------------------------------

def test_admin_settings_response_with_legal_urls():
    now = datetime.now(UTC)
    resp = AdminSettingsResponse(
        shop_name="Победа",
        phone="+79991112233",
        currency="RUB",
        delivery_enabled=True,
        pickup_enabled=True,
        online_payment_enabled=True,
        pay_on_delivery_enabled=True,
        min_order_amount=Decimal("500.00"),
        maintenance_mode=False,
        privacy_policy_url="/privacy",
        user_agreement_url="/offer",
        personal_data_consent_url="/personal-data-consent",
        updated_at=now,
    )
    assert resp.privacy_policy_url == "/privacy"
    assert resp.user_agreement_url == "/offer"
    assert resp.personal_data_consent_url == "/personal-data-consent"


# ---------------------------------------------------------
# 3. Интеграция AdminSettingsService
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_settings_service_update_legal_urls():
    session = AsyncMock()
    commiter = AsyncMock()
    audit_repo = AsyncMock()
    settings_cache = AsyncMock()
    delivery_cache = AsyncMock()
    cart_cache = AsyncMock()
    redis_service = AsyncMock()

    user = User(id=1, name="Администратор", role=UserRole.ADMIN, is_active=True)

    store_settings = StoreSettings(
        shop_name="Победа",
        online_payment_enabled=True,
        pay_on_delivery_enabled=True,
        maintenance_mode=False,
        privacy_policy_url="/privacy",
        user_agreement_url="/offer",
        personal_data_consent_url="/personal-data-consent",
    )
    delivery_settings = SimpleNamespace(
        default_city="Кизляр",
        currency="RUB",
        delivery_enabled=True,
        pickup_enabled=True,
        min_order_amount=Decimal("300.00"),
        updated_at=None,
    )

    settings_repo = AsyncMock()
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    async def fake_update(session, store_settings, data):
        for k, v in data.items():
            setattr(store_settings, k, v)
        return store_settings

    settings_repo.update.side_effect = fake_update

    delivery_repo = AsyncMock()
    delivery_repo.get_or_create_default.return_value = (delivery_settings, False)

    permission_service = MagicMock()
    permission_service.get_user_permissions.return_value = {"admin:settings:update"}
    audit_log_service = AsyncMock()

    service = AdminSettingsService()
    update_data = AdminSettingsUpdateRequest(
        privacy_policy_url="https://site.ru/custom-privacy",
        user_agreement_url="https://site.ru/custom-offer",
    )

    response = await service.update_settings(
        session=session,
        commiter=commiter,
        settings_repository=settings_repo,
        delivery_settings_repository=delivery_repo,
        admin_audit_log_repository=audit_repo,
        permission_service=permission_service,
        audit_log_service=audit_log_service,
        settings_cache_service=settings_cache,
        delivery_cache_service=delivery_cache,
        cart_cache_service=cart_cache,
        redis_service=redis_service,
        user=user,
        data=update_data,
        ip_address="127.0.0.1",
        user_agent="pytest-client",
    )

    assert store_settings.privacy_policy_url == "https://site.ru/custom-privacy"
    assert store_settings.user_agreement_url == "https://site.ru/custom-offer"
    assert commiter.commit.called
    assert settings_cache.invalidate_public_settings.called
