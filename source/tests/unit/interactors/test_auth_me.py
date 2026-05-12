from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import CurrentUserNotFoundError, InactiveUserError
from source.interactors.auth_me import AuthMeInteractor
from source.schemas.pydantic.auth import CurrentUserResponse
from source.services.auth import AuthService


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, execute_results: list | None = None) -> None:
        self.execute_results = execute_results or []
        self.executed_count = 0

    async def execute(self, statement):
        self.executed_count += 1
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)


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

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds


def build_user(*, is_active: bool = True) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash="password_hash",
        role=UserRole.CUSTOMER,
        is_active=is_active,
    )
    user.id = 1
    user.created_date = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    return user


def build_access_token(*, auth_service: AuthService | None = None) -> str:
    auth_service = auth_service or AuthService()
    return auth_service.create_access_token(user_id=1, role=UserRole.CUSTOMER)


def build_expired_access_token() -> str:
    return jwt.encode(
        claims={
            "sub": "1",
            "user_id": 1,
            "role": UserRole.CUSTOMER.value,
            "token_type": "access",
            "jti": "expired-token-id",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        key=settings.auth.jwt_secret_key,
        algorithm=settings.auth.jwt_algorithm,
    )


@pytest.mark.asyncio
async def test_get_me_from_postgresql_success() -> None:
    session = FakeSession(execute_results=[build_user()])
    redis_service = FakeRedisService()

    response = await AuthMeInteractor().execute(
        session=session,
        auth_service=AuthService(),
        redis_service=redis_service,
        user_id=1,
    )

    assert response.id == 1
    assert response.role == UserRole.CUSTOMER
    assert response.permissions == ["profile:read", "orders:read", "orders:create"]
    assert session.executed_count == 1


@pytest.mark.asyncio
async def test_get_me_from_redis_cache_success() -> None:
    cached_response = CurrentUserResponse(
        id=1,
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        role=UserRole.CUSTOMER,
        permissions=["profile:read"],
        is_active=True,
        is_verified=False,
        created_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC),
    )
    session = FakeSession()
    redis_service = FakeRedisService()
    redis_service.values["auth:me:user:1"] = cached_response.model_dump_json()

    response = await AuthMeInteractor().execute(
        session=session,
        auth_service=AuthService(),
        redis_service=redis_service,
        user_id=1,
    )

    assert response.id == 1
    assert response.permissions == ["profile:read"]
    assert session.executed_count == 0


@pytest.mark.asyncio
async def test_get_me_without_authorization_header() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_invalid_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization="Bearer invalid-token", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_expired_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(
            authorization=f"Bearer {build_expired_access_token()}",
            redis_service=FakeRedisService(),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_refresh_token_instead_of_access_token() -> None:
    auth_service = AuthService()
    refresh_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(
            authorization=f"Bearer {refresh_token}",
            redis_service=FakeRedisService(),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_blacklisted_access_token(monkeypatch) -> None:
    monkeypatch.setattr(settings.change_password, "jwt_access_blacklist_enabled", True)
    access_token = build_access_token()
    payload = jwt.decode(
        token=access_token,
        key=settings.auth.jwt_secret_key,
        algorithms=[settings.auth.jwt_algorithm],
    )
    redis_service = FakeRedisService()
    redis_service.values[f"auth:blacklist:access:{payload['jti']}"] = "revoked"

    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(
            authorization=f"Bearer {access_token}",
            redis_service=redis_service,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_me_user_not_found() -> None:
    with pytest.raises(CurrentUserNotFoundError):
        await AuthMeInteractor().execute(
            session=FakeSession(execute_results=[None]),
            auth_service=AuthService(),
            redis_service=FakeRedisService(),
            user_id=1,
        )


@pytest.mark.asyncio
async def test_get_me_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        await AuthMeInteractor().execute(
            session=FakeSession(execute_results=[build_user(is_active=False)]),
            auth_service=AuthService(),
            redis_service=FakeRedisService(),
            user_id=1,
        )


@pytest.mark.asyncio
async def test_get_me_response_does_not_include_password_hash() -> None:
    response = await AuthMeInteractor().execute(
        session=FakeSession(execute_results=[build_user()]),
        auth_service=AuthService(),
        redis_service=FakeRedisService(),
        user_id=1,
    )

    response_data = response.model_dump()
    assert "password_hash" not in response_data
    assert "refresh_token" not in response_data


@pytest.mark.asyncio
async def test_get_me_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()

    await AuthMeInteractor().execute(
        session=FakeSession(execute_results=[build_user()]),
        auth_service=AuthService(),
        redis_service=redis_service,
        user_id=1,
    )

    assert "auth:me:user:1" in redis_service.values
    assert redis_service.ttls["auth:me:user:1"] == 120


@pytest.mark.asyncio
async def test_get_me_cache_can_be_invalidated() -> None:
    redis_service = FakeRedisService()
    redis_service.values["auth:me:user:1"] = "{}"

    await AuthService().invalidate_current_user_cache(
        redis_service=redis_service,
        user_id=1,
    )

    assert "auth:me:user:1" in redis_service.deleted
    assert "auth:me:user:1" not in redis_service.values
