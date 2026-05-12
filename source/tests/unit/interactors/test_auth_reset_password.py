import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    InvalidPasswordResetTokenError,
    NewPasswordSameAsOldError,
    PasswordResetUserNotFoundError,
)
from source.interactors.auth_reset_password import AuthResetPasswordInteractor
from source.schemas.pydantic.auth import ResetPasswordRequest
from source.services.auth import AuthService, RESET_PASSWORD_SUCCESS_MESSAGE


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, execute_results: list | None = None, refresh_tokens: list[RefreshToken] | None = None) -> None:
        self.execute_results = execute_results or []
        self.refresh_tokens = refresh_tokens or []
        self.added = []
        self.flush_called = False
        self.revoked_refresh_tokens_count = 0

    async def execute(self, statement):
        if getattr(statement, "is_update", False):
            now = datetime.now(UTC)
            for refresh_token in self.refresh_tokens:
                if refresh_token.revoked_at is None:
                    refresh_token.revoked_at = now
                    self.revoked_refresh_tokens_count += 1
            return FakeScalarResult(None)

        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_called = True


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, ttl_seconds: int) -> None:
        return None


def build_user(
    *,
    auth_service: AuthService,
    password: str = "OldStrongPassword123",
    is_active: bool = True,
) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash=auth_service.hash_password(password),
        role=UserRole.CUSTOMER,
        is_active=is_active,
    )
    user.id = 1
    return user


def build_refresh_token(*, revoked_at: datetime | None = None) -> RefreshToken:
    refresh_token = RefreshToken(
        user_id=1,
        token_hash="refresh_token_hash",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        revoked_at=revoked_at,
    )
    refresh_token.id = 1
    return refresh_token


def store_reset_token(
    *,
    auth_service: AuthService,
    redis_service: FakeRedisService,
    plain_token: str = "plain-reset-token",
    user_id: int = 1,
) -> str:
    token_hash = auth_service.hash_password_reset_token(plain_token)
    redis_service.values[f"password_reset:token:{token_hash}"] = json.dumps(
        {
            "user_id": user_id,
            "created_at": "2026-05-12T10:00:00",
            "ip_address": "127.0.0.1",
            "user_agent": "pytest",
        },
    )
    redis_service.values[f"password_reset:user:{user_id}"] = token_hash
    return token_hash


async def execute_reset_password(
    *,
    user: User | None,
    redis_service: FakeRedisService | None = None,
    new_password: str = "NewStrongPassword123",
    plain_token: str = "plain-reset-token",
    refresh_tokens: list[RefreshToken] | None = None,
) -> tuple:
    auth_service = AuthService()
    redis_service = redis_service or FakeRedisService()
    session = FakeSession(execute_results=[user], refresh_tokens=refresh_tokens)

    response = await AuthResetPasswordInteractor().execute(
        session=session,
        auth_service=auth_service,
        redis_service=redis_service,
        data=ResetPasswordRequest(
            token=plain_token,
            new_password=new_password,
            new_password_confirm=new_password,
        ),
    )
    return response, session, redis_service, auth_service


@pytest.mark.asyncio
async def test_reset_password_success() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    token_hash = store_reset_token(auth_service=auth_service, redis_service=redis_service)
    user = build_user(auth_service=auth_service)

    response, session, _, auth_service = await execute_reset_password(
        user=user,
        redis_service=redis_service,
    )

    assert response.message == RESET_PASSWORD_SUCCESS_MESSAGE
    assert auth_service.verify_password("NewStrongPassword123", user.password_hash)
    assert f"password_reset:token:{token_hash}" in redis_service.deleted


def test_reset_password_passwords_do_not_match() -> None:
    with pytest.raises(ValidationError):
        ResetPasswordRequest(
            token="plain-reset-token",
            new_password="NewStrongPassword123",
            new_password_confirm="AnotherStrongPassword123",
        )


def test_reset_password_weak_password() -> None:
    with pytest.raises(ValidationError):
        ResetPasswordRequest(
            token="plain-reset-token",
            new_password="weakpassword",
            new_password_confirm="weakpassword",
        )


@pytest.mark.asyncio
async def test_reset_password_same_as_old_password() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)
    user = build_user(auth_service=auth_service)

    with pytest.raises(NewPasswordSameAsOldError):
        await execute_reset_password(
            user=user,
            redis_service=redis_service,
            new_password="OldStrongPassword123",
        )


@pytest.mark.asyncio
async def test_reset_password_missing_redis_token() -> None:
    auth_service = AuthService()

    with pytest.raises(InvalidPasswordResetTokenError):
        await execute_reset_password(
            user=build_user(auth_service=auth_service),
            redis_service=FakeRedisService(),
        )


@pytest.mark.asyncio
async def test_reset_password_expired_redis_token() -> None:
    auth_service = AuthService()

    with pytest.raises(InvalidPasswordResetTokenError):
        await execute_reset_password(
            user=build_user(auth_service=auth_service),
            redis_service=FakeRedisService(),
            plain_token="expired-plain-token",
        )


@pytest.mark.asyncio
async def test_reset_password_user_not_found() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)

    with pytest.raises(PasswordResetUserNotFoundError):
        await execute_reset_password(user=None, redis_service=redis_service)


@pytest.mark.asyncio
async def test_reset_password_inactive_user() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)

    with pytest.raises(InactiveUserError):
        await execute_reset_password(
            user=build_user(auth_service=auth_service, is_active=False),
            redis_service=redis_service,
        )


@pytest.mark.asyncio
async def test_reset_password_token_key_deleted_after_success() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    token_hash = store_reset_token(auth_service=auth_service, redis_service=redis_service)

    await execute_reset_password(
        user=build_user(auth_service=auth_service),
        redis_service=redis_service,
    )

    assert f"password_reset:token:{token_hash}" in redis_service.deleted
    assert f"password_reset:token:{token_hash}" not in redis_service.values


@pytest.mark.asyncio
async def test_reset_password_user_key_deleted_after_success() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)

    await execute_reset_password(
        user=build_user(auth_service=auth_service),
        redis_service=redis_service,
    )

    assert "password_reset:user:1" in redis_service.deleted
    assert "password_reset:user:1" not in redis_service.values


@pytest.mark.asyncio
async def test_reset_password_revokes_old_refresh_tokens() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)
    active_refresh_token = build_refresh_token()
    revoked_refresh_token = build_refresh_token(revoked_at=datetime.now(UTC))

    _, session, _, _ = await execute_reset_password(
        user=build_user(auth_service=auth_service),
        redis_service=redis_service,
        refresh_tokens=[active_refresh_token, revoked_refresh_token],
    )

    assert session.revoked_refresh_tokens_count == 1
    assert active_refresh_token.revoked_at is not None


@pytest.mark.asyncio
async def test_reset_password_response_does_not_include_new_password() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)

    response, _, _, _ = await execute_reset_password(
        user=build_user(auth_service=auth_service),
        redis_service=redis_service,
    )

    response_data = response.model_dump()
    assert "new_password" not in response_data
    assert "password_hash" not in response_data


@pytest.mark.asyncio
async def test_plain_reset_token_is_not_stored_in_redis() -> None:
    auth_service = AuthService()
    redis_service = FakeRedisService()
    store_reset_token(auth_service=auth_service, redis_service=redis_service)

    assert "plain-reset-token" not in json.dumps(redis_service.values)
