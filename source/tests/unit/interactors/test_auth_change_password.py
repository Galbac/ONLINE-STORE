from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import resolve_current_user
from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    ChangePasswordRateLimitExceededError,
    InvalidCurrentPasswordError,
    NewPasswordSameAsOldError,
)
from source.interactors.auth_change_password import AuthChangePasswordInteractor
from source.schemas.pydantic.auth import ChangePasswordRequest
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
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)
        self.ttls.pop(key, None)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds


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


async def execute_change_password(
    *,
    user: User,
    redis_service: FakeRedisService | None = None,
    current_password: str = "OldStrongPassword123",
    new_password: str = "NewStrongPassword123",
    refresh_tokens: list[RefreshToken] | None = None,
) -> tuple:
    auth_service = AuthService()
    redis_service = redis_service or FakeRedisService()
    session = FakeSession(refresh_tokens=refresh_tokens)

    response = await AuthChangePasswordInteractor().execute(
        session=session,
        auth_service=auth_service,
        redis_service=redis_service,
        user=user,
        data=ChangePasswordRequest(
            current_password=current_password,
            new_password=new_password,
            new_password_confirm=new_password,
        ),
        ip_address="127.0.0.1",
        access_token=None,
    )
    return response, session, redis_service, auth_service


@pytest.mark.asyncio
async def test_change_password_success() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)

    response, _, _, auth_service = await execute_change_password(user=user)

    assert response.message == RESET_PASSWORD_SUCCESS_MESSAGE
    assert auth_service.verify_password("NewStrongPassword123", user.password_hash)


@pytest.mark.asyncio
async def test_change_password_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(authorization=None, session=FakeSession())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_change_password_with_invalid_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(authorization="Bearer invalid-token", session=FakeSession())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_change_password_with_refresh_token_instead_of_access_token() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)
    refresh_token = auth_service.create_refresh_token(user_id=user.id, role=user.role)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_current_user(
            authorization=f"Bearer {refresh_token}",
            session=FakeSession(execute_results=[user]),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_change_password_wrong_current_password() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)

    with pytest.raises(InvalidCurrentPasswordError):
        await execute_change_password(user=user, current_password="WrongPassword123")


@pytest.mark.asyncio
async def test_change_password_failed_attempts_limit() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)
    redis_service = FakeRedisService()
    redis_service.values["auth:change_password:failed:user:1"] = "4"

    with pytest.raises(ChangePasswordRateLimitExceededError):
        await execute_change_password(
            user=user,
            redis_service=redis_service,
            current_password="WrongPassword123",
        )


def test_change_password_passwords_do_not_match() -> None:
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            current_password="OldStrongPassword123",
            new_password="NewStrongPassword123",
            new_password_confirm="AnotherStrongPassword123",
        )


def test_change_password_weak_new_password() -> None:
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            current_password="OldStrongPassword123",
            new_password="weakpassword",
            new_password_confirm="weakpassword",
        )


@pytest.mark.asyncio
async def test_change_password_same_as_old_password() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)

    with pytest.raises(NewPasswordSameAsOldError):
        await execute_change_password(user=user, new_password="OldStrongPassword123")


@pytest.mark.asyncio
async def test_change_password_revokes_old_refresh_tokens() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)
    active_refresh_token = build_refresh_token()
    revoked_refresh_token = build_refresh_token(revoked_at=datetime.now(UTC))

    _, session, _, _ = await execute_change_password(
        user=user,
        refresh_tokens=[active_refresh_token, revoked_refresh_token],
    )

    assert session.revoked_refresh_tokens_count == 1
    assert active_refresh_token.revoked_at is not None


@pytest.mark.asyncio
async def test_change_password_deletes_reset_password_tokens() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)
    redis_service = FakeRedisService()
    redis_service.values["password_reset:user:1"] = "old-token-hash"
    redis_service.values["password_reset:token:old-token-hash"] = "{}"

    await execute_change_password(user=user, redis_service=redis_service)

    assert "password_reset:user:1" in redis_service.deleted
    assert "password_reset:token:old-token-hash" in redis_service.deleted


@pytest.mark.asyncio
async def test_change_password_rate_limit_by_user() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)
    redis_service = FakeRedisService()
    redis_service.values["auth:change_password:rate:user:1"] = "5"

    with pytest.raises(ChangePasswordRateLimitExceededError):
        await execute_change_password(user=user, redis_service=redis_service)


@pytest.mark.asyncio
async def test_change_password_rate_limit_by_ip() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)
    redis_service = FakeRedisService()
    redis_service.values["auth:change_password:rate:ip:127.0.0.1"] = "10"

    with pytest.raises(ChangePasswordRateLimitExceededError):
        await execute_change_password(user=user, redis_service=redis_service)


@pytest.mark.asyncio
async def test_change_password_response_does_not_include_password_hash() -> None:
    auth_service = AuthService()
    user = build_user(auth_service=auth_service)

    response, _, _, _ = await execute_change_password(user=user)

    response_data = response.model_dump()
    assert "password_hash" not in response_data
    assert "new_password" not in response_data
