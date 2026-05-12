from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi import HTTPException

from source.api.dependencies import resolve_current_user
from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
)
from source.interactors.auth_logout import AuthLogoutInteractor
from source.services.auth import AuthService


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, execute_results: list | None = None) -> None:
        self.execute_results = execute_results or []
        self.added = []

    async def execute(self, statement):
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        return None


def build_user(*, user_id: int = 1) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash="hash",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user.id = user_id
    return user


def build_refresh_token(
    *,
    raw_token: str,
    user_id: int = 1,
    revoked_at: datetime | None = None,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user_id,
        token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=30),
        revoked_at=revoked_at,
    )
    token.id = 1
    return token


@pytest.mark.asyncio
async def test_logout_success() -> None:
    auth_service = AuthService()
    raw_token = "jwt_refresh_token"
    refresh_token = build_refresh_token(raw_token=raw_token)
    session = FakeSession(execute_results=[refresh_token])

    await AuthLogoutInteractor().execute(
        session=session,
        auth_service=auth_service,
        user=build_user(),
        refresh_token=raw_token,
    )

    assert refresh_token.revoked_at is not None
    assert session.added[0] is refresh_token


@pytest.mark.asyncio
async def test_logout_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(authorization=None, session=FakeSession())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_wrong_refresh_token() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[None])

    with pytest.raises(RefreshTokenNotFoundError):
        await AuthLogoutInteractor().execute(
            session=session,
            auth_service=auth_service,
            user=build_user(),
            refresh_token="wrong_refresh_token",
        )


@pytest.mark.asyncio
async def test_logout_with_another_user_refresh_token() -> None:
    auth_service = AuthService()
    raw_token = "jwt_refresh_token"
    session = FakeSession(execute_results=[build_refresh_token(raw_token=raw_token, user_id=2)])

    with pytest.raises(RefreshTokenNotFoundError):
        await AuthLogoutInteractor().execute(
            session=session,
            auth_service=auth_service,
            user=build_user(user_id=1),
            refresh_token=raw_token,
        )


@pytest.mark.asyncio
async def test_logout_with_already_revoked_refresh_token() -> None:
    auth_service = AuthService()
    raw_token = "jwt_refresh_token"
    session = FakeSession(
        execute_results=[
            build_refresh_token(
                raw_token=raw_token,
                revoked_at=datetime.now(UTC),
            ),
        ],
    )

    with pytest.raises(RefreshTokenAlreadyRevokedError):
        await AuthLogoutInteractor().execute(
            session=session,
            auth_service=auth_service,
            user=build_user(),
            refresh_token=raw_token,
        )
