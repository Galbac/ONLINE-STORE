from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.schemas.pydantic.auth import UserRegisterRequest
from source.schemas.pydantic.user import (
    AdminUserListItemResponse,
    UserMeResponse,
    UserMeUpdateRequest,
)
from source.services.auth import AuthService


# ---------------------------------------------------------
# 1. Валидация UserRegisterRequest (152-ФЗ и 38-ФЗ)
# ---------------------------------------------------------

def test_register_request_privacy_true_is_valid() -> None:
    req = UserRegisterRequest(
        name="Алексей",
        phone="+79991112233",
        email="alexey@example.com",
        otp_code="1234",
        password="SecurePassword123!",
        agreed_to_privacy=True,
        marketing_consent=False,
    )
    assert req.agreed_to_privacy is True
    assert req.marketing_consent is False


def test_register_request_privacy_default_is_true() -> None:
    req = UserRegisterRequest(
        name="Алексей",
        phone="+79991112233",
        email="alexey@example.com",
        otp_code="1234",
        password="SecurePassword123!",
    )
    assert req.agreed_to_privacy is True
    assert req.marketing_consent is False


def test_register_request_privacy_false_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc:
        UserRegisterRequest(
            name="Алексей",
            phone="+79991112233",
            email="alexey@example.com",
            otp_code="1234",
            password="SecurePassword123!",
            agreed_to_privacy=False,
        )
    assert "Необходимо дать согласие на обработку персональных данных" in str(exc.value)


def test_register_request_marketing_consent_can_be_true() -> None:
    req = UserRegisterRequest(
        name="Мария",
        phone="+79992223344",
        email="maria@example.com",
        otp_code="5678",
        password="SecurePassword123!",
        agreed_to_privacy=True,
        marketing_consent=True,
    )
    assert req.marketing_consent is True


def test_register_request_marketing_consent_falsy_values() -> None:
    req = UserRegisterRequest(
        name="Иван",
        phone="+79993334455",
        email="ivan@example.com",
        otp_code="9999",
        password="SecurePassword123!",
        agreed_to_privacy=True,
        marketing_consent=False,
    )
    assert req.marketing_consent is False


# ---------------------------------------------------------
# 2. Валидация UserMeUpdateRequest (изменение согласий)
# ---------------------------------------------------------

def test_user_me_update_marketing_consent_toggle_on() -> None:
    req = UserMeUpdateRequest(marketing_consent=True)
    assert req.marketing_consent is True


def test_user_me_update_marketing_consent_toggle_off() -> None:
    req = UserMeUpdateRequest(marketing_consent=False)
    assert req.marketing_consent is False


def test_user_me_update_marketing_consent_none() -> None:
    req = UserMeUpdateRequest(name="Новое имя")
    assert req.marketing_consent is None


# ---------------------------------------------------------
# 3. Сериализация UserMeResponse (проверка согласий профиля)
# ---------------------------------------------------------

def test_user_me_response_with_consents() -> None:
    now = datetime.now(UTC)
    resp = UserMeResponse(
        id=1,
        name="Ольга",
        phone="+79994445566",
        email="olga@example.com",
        role=UserRole.CUSTOMER,
        is_active=True,
        agreed_to_privacy=True,
        agreed_to_privacy_at=now,
        marketing_consent=True,
        marketing_consent_at=now,
        created_at=now,
        updated_at=now,
    )
    assert resp.agreed_to_privacy is True
    assert resp.agreed_to_privacy_at == now
    assert resp.marketing_consent is True
    assert resp.marketing_consent_at == now


def test_user_me_response_defaults_for_consents() -> None:
    now = datetime.now(UTC)
    resp = UserMeResponse(
        id=2,
        name="Павел",
        phone="+79995556677",
        email=None,
        role=UserRole.CUSTOMER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert resp.agreed_to_privacy is True
    assert resp.agreed_to_privacy_at is None
    assert resp.marketing_consent is False
    assert resp.marketing_consent_at is None


# ---------------------------------------------------------
# 4. Сериализация AdminUserListItemResponse
# ---------------------------------------------------------

def test_admin_user_list_item_with_marketing_consent() -> None:
    now = datetime.now(UTC)
    item = AdminUserListItemResponse(
        id=1,
        name="Клиент 1",
        phone="+79997778899",
        email="client1@example.com",
        is_active=True,
        is_blocked=False,
        agreed_to_privacy=True,
        marketing_consent=True,
        orders_count=5,
        total_spent=Decimal("12500.50"),
        created_at=now,
    )
    assert item.marketing_consent is True
    assert item.agreed_to_privacy is True


def test_admin_user_list_item_without_marketing_consent() -> None:
    now = datetime.now(UTC)
    item = AdminUserListItemResponse(
        id=2,
        name="Клиент 2",
        phone="+79998889900",
        email=None,
        is_active=True,
        is_blocked=False,
        agreed_to_privacy=True,
        marketing_consent=False,
        orders_count=0,
        total_spent=Decimal("0.00"),
        created_at=now,
    )
    assert item.marketing_consent is False
    assert item.agreed_to_privacy is True
