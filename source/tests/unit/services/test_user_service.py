from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.user import UserMeResponse, UserMeUpdateRequest
from source.services.auth_cache import AuthCacheService
from source.services.auth import AuthService
from source.services.user import UserService
from source.services.user_cache import UserCacheService


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, execute_results: list | None = None) -> None:
        self.execute_results = execute_results or []
        self.executed_count = 0
        self.added = []
        self.flush_called = False
        self.refresh_called = False

    async def execute(self, statement):
        self.executed_count += 1
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_called = True

    async def refresh(self, instance) -> None:
        self.refresh_called = True


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
    user.updated_date = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    return user


async def execute_get_current_user_profile(
    *,
    session: FakeSession,
    redis_service: FakeRedisService | None = None,
) -> UserMeResponse:
    return await UserService().get_current_user_profile(
        session=session,
        redis_service=redis_service or FakeRedisService(),
        user_cache_service=UserCacheService(),
        user_id=1,
    )


async def execute_update_current_user_profile(
    *,
    session: FakeSession,
    redis_service: FakeRedisService | None = None,
    data: UserMeUpdateRequest,
) -> UserMeResponse:
    return await UserService().update_current_user_profile(
        session=session,
        redis_service=redis_service or FakeRedisService(),
        user_cache_service=UserCacheService(),
        auth_cache_service=AuthCacheService(),
        user_id=1,
        data=data,
    )


@pytest.mark.asyncio
async def test_get_user_me_from_postgresql_success() -> None:
    session = FakeSession(execute_results=[build_user()])

    response = await execute_get_current_user_profile(session=session)

    assert response.id == 1
    assert response.name == "Иван Иванов"
    assert response.role == UserRole.CUSTOMER
    assert response.is_active is True
    assert response.is_verified is False
    assert response.created_at == datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    assert response.updated_at == datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    assert session.executed_count == 1


@pytest.mark.asyncio
async def test_get_user_me_from_redis_cache_success() -> None:
    session = FakeSession()
    redis_service = FakeRedisService()
    cached_response = UserMeResponse(
        id=1,
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=False,
        created_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC),
    )
    redis_service.values["users:me:1"] = cached_response.model_dump_json()

    response = await execute_get_current_user_profile(
        session=session,
        redis_service=redis_service,
    )

    assert response.id == 1
    assert response.email == "ivan@example.com"
    assert session.executed_count == 0


@pytest.mark.asyncio
async def test_get_user_me_user_not_found() -> None:
    with pytest.raises(CurrentUserNotFoundError):
        await execute_get_current_user_profile(session=FakeSession(execute_results=[None]))


@pytest.mark.asyncio
async def test_get_user_me_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        await execute_get_current_user_profile(session=FakeSession(execute_results=[build_user(is_active=False)]))


@pytest.mark.asyncio
async def test_get_user_me_response_does_not_include_password_hash() -> None:
    response = await execute_get_current_user_profile(session=FakeSession(execute_results=[build_user()]))

    response_data = response.model_dump()
    assert "password_hash" not in response_data
    assert "refresh_token" not in response_data


@pytest.mark.asyncio
async def test_get_user_me_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()

    await execute_get_current_user_profile(
        session=FakeSession(execute_results=[build_user()]),
        redis_service=redis_service,
    )

    assert "users:me:1" in redis_service.values
    assert redis_service.ttls["users:me:1"] == settings.user_me.cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_user_me_cache_can_be_invalidated() -> None:
    redis_service = FakeRedisService()
    redis_service.values["users:me:1"] = "{}"

    await UserCacheService().delete_user_me_cache(
        redis_service=redis_service,
        user_id=1,
    )

    assert "users:me:1" in redis_service.deleted
    assert "users:me:1" not in redis_service.values


@pytest.mark.asyncio
async def test_get_user_me_with_blacklisted_access_token(monkeypatch) -> None:
    monkeypatch.setattr(settings.change_password, "jwt_access_blacklist_enabled", True)
    access_token = AuthService().create_access_token(user_id=1, role=UserRole.CUSTOMER)
    payload = await resolve_access_token(
        authorization=f"Bearer {access_token}",
        redis_service=FakeRedisService(),
    )
    redis_service = FakeRedisService()
    redis_service.values[f"auth:blacklist:access:{payload['jti']}"] = "revoked"

    with pytest.raises(Exception) as exc_info:
        await resolve_access_token(
            authorization=f"Bearer {access_token}",
            redis_service=redis_service,
        )

    assert getattr(exc_info.value, "status_code") == 401


@pytest.mark.asyncio
async def test_update_user_me_name_success() -> None:
    user = build_user()
    session = FakeSession(execute_results=[user])

    response = await execute_update_current_user_profile(
        session=session,
        data=UserMeUpdateRequest(name="Иван Петров"),
    )

    assert response.name == "Иван Петров"
    assert user.name == "Иван Петров"
    assert session.flush_called is True
    assert session.refresh_called is True


@pytest.mark.asyncio
async def test_update_user_me_phone_success() -> None:
    user = build_user()
    session = FakeSession(execute_results=[user, None])

    response = await execute_update_current_user_profile(
        session=session,
        data=UserMeUpdateRequest(phone="+79991112233"),
    )

    assert response.phone == "+79991112233"
    assert user.phone == "+79991112233"
    assert session.executed_count == 2


@pytest.mark.asyncio
async def test_update_user_me_email_success() -> None:
    user = build_user()
    session = FakeSession(execute_results=[user, None])

    response = await execute_update_current_user_profile(
        session=session,
        data=UserMeUpdateRequest(email="IVAN.PETROV@example.com"),
    )

    assert response.email == "ivan.petrov@example.com"
    assert user.email == "ivan.petrov@example.com"
    assert response.is_verified is False


@pytest.mark.asyncio
async def test_update_user_me_multiple_fields_success() -> None:
    user = build_user()
    session = FakeSession(execute_results=[user, None, None])

    response = await execute_update_current_user_profile(
        session=session,
        data=UserMeUpdateRequest(
            name="Иван Петров",
            phone="+79991112233",
            email="ivan.petrov@example.com",
        ),
    )

    assert response.name == "Иван Петров"
    assert response.phone == "+79991112233"
    assert response.email == "ivan.petrov@example.com"
    assert session.executed_count == 3


@pytest.mark.asyncio
async def test_update_user_me_without_fields() -> None:
    with pytest.raises(EmptyUserProfileUpdateError):
        await execute_update_current_user_profile(
            session=FakeSession(execute_results=[build_user()]),
            data=UserMeUpdateRequest(),
        )


def test_update_user_me_with_invalid_phone() -> None:
    with pytest.raises(ValidationError):
        UserMeUpdateRequest(phone="not-phone")


def test_update_user_me_with_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserMeUpdateRequest(email="not-email")


@pytest.mark.asyncio
async def test_update_user_me_with_existing_phone() -> None:
    with pytest.raises(UserPhoneAlreadyExistsError):
        await execute_update_current_user_profile(
            session=FakeSession(execute_results=[build_user(), 2]),
            data=UserMeUpdateRequest(phone="+79991112233"),
        )


@pytest.mark.asyncio
async def test_update_user_me_with_existing_email() -> None:
    with pytest.raises(UserEmailAlreadyExistsError):
        await execute_update_current_user_profile(
            session=FakeSession(execute_results=[build_user(), 2]),
            data=UserMeUpdateRequest(email="ivan.petrov@example.com"),
        )


@pytest.mark.asyncio
async def test_update_user_me_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_update_user_me_with_invalid_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization="Bearer invalid-token", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_update_user_me_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        await execute_update_current_user_profile(
            session=FakeSession(execute_results=[build_user(is_active=False)]),
            data=UserMeUpdateRequest(name="Иван Петров"),
        )


@pytest.mark.asyncio
async def test_update_user_me_cannot_change_role() -> None:
    user = build_user()
    session = FakeSession(execute_results=[user])

    response = await execute_update_current_user_profile(
        session=session,
        data=UserMeUpdateRequest.model_validate({"name": "Иван Петров", "role": "admin"}),
    )

    assert response.role == UserRole.CUSTOMER
    assert user.role == UserRole.CUSTOMER


@pytest.mark.asyncio
async def test_update_user_me_response_does_not_include_password_hash() -> None:
    response = await execute_update_current_user_profile(
        session=FakeSession(execute_results=[build_user()]),
        data=UserMeUpdateRequest(name="Иван Петров"),
    )

    response_data = response.model_dump()
    assert "password_hash" not in response_data
    assert "refresh_token" not in response_data


@pytest.mark.asyncio
async def test_update_user_me_invalidates_redis_cache() -> None:
    redis_service = FakeRedisService()
    redis_service.values["users:me:1"] = "{}"
    redis_service.values["auth:me:user:1"] = "{}"

    await execute_update_current_user_profile(
        session=FakeSession(execute_results=[build_user()]),
        redis_service=redis_service,
        data=UserMeUpdateRequest(name="Иван Петров"),
    )

    assert "users:me:1" in redis_service.deleted
    assert "auth:me:user:1" in redis_service.deleted
    assert "users:me:1" not in redis_service.values
    assert "auth:me:user:1" not in redis_service.values
