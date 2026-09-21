from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.auth import (
    forgot_password,
    get_me,
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
    reset_password,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidRefreshTokenError,
)
from source.schemas.pydantic.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterAuthResponse,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserShortResponse,
)
from source.schemas.pydantic.user import UserMeResponse


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)


@pytest.fixture
def fake_auth_user():
    return UserShortResponse(
        id=1,
        name="Иван",
        phone="+79991234567",
        email="ivan@example.com",
        role=UserRole.CUSTOMER,
        is_active=True,
    )


@pytest.fixture
def fake_request():
    req = MagicMock()
    req.client = SimpleNamespace(host="127.0.0.1")
    req.headers = {"user-agent": "pytest"}
    return req


# ---------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_me_success():
    now = datetime.now(UTC)
    interactor = AsyncMock()
    interactor.execute.return_value = UserMeResponse(
        id=1,
        name="Иван",
        phone="+79991234567",
        email="ivan@example.com",
        role=UserRole.CUSTOMER,
        is_active=True,
        agreed_to_privacy=True,
        marketing_consent=False,
        created_at=now,
        updated_at=now,
    )

    response = await unwrap(get_me)(
        token_payload={"user_id": 1},
        session=AsyncMock(),
        auth_service=AsyncMock(),
        redis_service=AsyncMock(),
        auth_me_interactor=interactor,
    )

    assert response.id == 1
    assert response.name == "Иван"


# ---------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_register_user_success():
    interactor = AsyncMock()
    interactor.execute.return_value = RegisterAuthResponse(
        id=1,
        name="Иван",
        phone="+79991234567",
        email="ivan@example.com",
        role=UserRole.CUSTOMER,
        is_active=True,
        access_token="access_token_123",
        refresh_token="refresh_token_123",
        token_type="bearer",
        expires_in=3600,
    )
    commiter = AsyncMock()

    body = UserRegisterRequest(
        name="Иван",
        phone="+79991234567",
        password="SecurePassword123!",
        agreed_to_privacy=True,
        marketing_consent=True,
    )

    response = await unwrap(register_user)(
        body=body,
        session=AsyncMock(),
        commiter=commiter,
        auth_service=AsyncMock(),
        auth_register_interactor=interactor,
    )

    assert response.id == 1
    assert response.access_token == "access_token_123"
    assert commiter.commit.called


# ---------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_login_user_success(fake_auth_user):
    interactor = AsyncMock()
    interactor.execute.return_value = AuthResponse(
        access_token="access_token_123",
        refresh_token="refresh_token_123",
        token_type="bearer",
        expires_in=3600,
        user=fake_auth_user,
    )
    commiter = AsyncMock()

    body = UserLoginRequest(login="+79991234567", password="SecurePassword123!")
    response = await unwrap(login_user)(
        body=body,
        session=AsyncMock(),
        commiter=commiter,
        auth_service=AsyncMock(),
        auth_login_interactor=interactor,
    )

    assert response.access_token == "access_token_123"
    assert response.user.id == 1
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_login_user_invalid_credentials():
    interactor = AsyncMock()
    interactor.execute.side_effect = InvalidCredentialsError
    commiter = AsyncMock()

    body = UserLoginRequest(login="+79991234567", password="WrongPassword")
    with pytest.raises(HTTPException) as exc:
        await unwrap(login_user)(
            body=body,
            session=AsyncMock(),
            commiter=commiter,
            auth_service=AsyncMock(),
            auth_login_interactor=interactor,
        )
    assert exc.value.status_code == 401
    assert commiter.rollback.called


# ---------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_tokens_success(fake_request, fake_auth_user):
    interactor = AsyncMock()
    interactor.execute.return_value = AuthResponse(
        access_token="new_access_123",
        refresh_token="new_refresh_123",
        token_type="bearer",
        expires_in=3600,
        user=fake_auth_user,
    )
    commiter = AsyncMock()

    body = RefreshTokenRequest(refresh_token="valid_refresh")
    response = await unwrap(refresh_tokens)(
        body=body,
        request=fake_request,
        session=AsyncMock(),
        commiter=commiter,
        auth_service=AsyncMock(),
        redis_service=AsyncMock(),
        auth_refresh_interactor=interactor,
    )

    assert response.access_token == "new_access_123"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_refresh_tokens_invalid(fake_request):
    interactor = AsyncMock()
    interactor.execute.side_effect = InvalidRefreshTokenError
    commiter = AsyncMock()

    body = RefreshTokenRequest(refresh_token="bad_token")
    with pytest.raises(HTTPException) as exc:
        await unwrap(refresh_tokens)(
            body=body,
            request=fake_request,
            session=AsyncMock(),
            commiter=commiter,
            auth_service=AsyncMock(),
            redis_service=AsyncMock(),
            auth_refresh_interactor=interactor,
        )
    assert exc.value.status_code == 401


# ---------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_user_success(active_user):
    interactor = AsyncMock()
    commiter = AsyncMock()

    body = LogoutRequest(refresh_token="some_token")
    response = await unwrap(logout_user)(
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        auth_service=AsyncMock(),
        auth_logout_interactor=interactor,
    )

    assert response.message == "Вы успешно вышли из аккаунта"
    assert commiter.commit.called


# ---------------------------------------------------------
# POST /auth/forgot-password & reset-password
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_forgot_password_success(fake_request):
    interactor = AsyncMock()
    interactor.execute.return_value = SimpleNamespace(message="Инструкции отправлены")

    body = ForgotPasswordRequest(login="+79991234567")
    response = await unwrap(forgot_password)(
        body=body,
        request=fake_request,
        session=AsyncMock(),
        auth_service=AsyncMock(),
        redis_service=AsyncMock(),
        email_service=AsyncMock(),
        telegram_service=AsyncMock(),
        auth_forgot_password_interactor=interactor,
    )

    assert "инструкции" in response.message.lower()


@pytest.mark.asyncio
async def test_reset_password_invalid_token():
    interactor = AsyncMock()
    interactor.execute.side_effect = InvalidPasswordResetTokenError
    commiter = AsyncMock()

    body = ResetPasswordRequest(
        token="invalid_token",
        new_password="NewPassword123!",
        new_password_confirm="NewPassword123!",
    )
    with pytest.raises(HTTPException) as exc:
        await unwrap(reset_password)(
            body=body,
            session=AsyncMock(),
            commiter=commiter,
            auth_service=AsyncMock(),
            redis_service=AsyncMock(),
            auth_reset_password_interactor=interactor,
        )
    assert exc.value.status_code == 401
    assert commiter.rollback.called
