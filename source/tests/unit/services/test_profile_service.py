from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import CurrentUserNotFoundError, InactiveUserError
from source.schemas.pydantic.profile import (
    ProfileAddressShortResponse,
    ProfileOrderShortResponse,
    ProfileSummaryResponse,
)
from source.services.auth import AuthService
from source.services.profile import ProfileService
from source.services.profile_cache import ProfileCacheService


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


class FakeUserRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.requested_user_id: int | None = None

    async def get_by_id(self, *, session, user_id: int) -> User | None:
        self.requested_user_id = user_id
        return self.user


class FakeAddressRepository:
    def __init__(self) -> None:
        self.default_address = ProfileAddressShortResponse(
            id=5,
            city="Москва",
            street="Тверская",
            house="10",
            apartment="15",
        )
        self.count = 2

    async def get_default_by_user_id(self, *, session, user_id: int):
        return self.default_address

    async def count_by_user_id(self, *, session, user_id: int) -> int:
        return self.count


class FakeOrderRepository:
    def __init__(self) -> None:
        self.count = 12
        self.active_order = ProfileOrderShortResponse(
            id=101,
            order_number="ORD-101",
            status="assembling",
            final_price=Decimal("3250.50"),
            created_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC),
        )
        self.recent_orders = [
            ProfileOrderShortResponse(
                id=100,
                order_number="ORD-100",
                status="completed",
                final_price=Decimal("2400.00"),
                created_at=datetime(2026, 5, 10, 10, 0, 0, tzinfo=UTC),
            ),
        ]
        self.recent_limit: int | None = None

    async def count_by_user_id(self, *, session, user_id: int) -> int:
        return self.count

    async def get_recent_by_user_id(self, *, session, user_id: int, limit: int = 5):
        self.recent_limit = limit
        return self.recent_orders

    async def get_active_by_user_id(self, *, session, user_id: int):
        return self.active_order


def build_user(*, user_id: int = 1, is_active: bool = True, is_deleted: bool = False) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash="password_hash",
        role=UserRole.CUSTOMER,
        is_active=is_active,
        is_deleted=is_deleted,
    )
    user.id = user_id
    user.created_date = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    user.updated_date = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    user.deleted_at = None
    return user


async def execute_get_profile_summary(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    address_repository: FakeAddressRepository | None = None,
    order_repository: FakeOrderRepository | None = None,
    user_id: int = 1,
) -> ProfileSummaryResponse:
    return await ProfileService().get_profile_summary(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        address_repository=address_repository or FakeAddressRepository(),
        order_repository=order_repository or FakeOrderRepository(),
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_get_profile_summary_from_postgresql_success() -> None:
    user_repository = FakeUserRepository(build_user())
    order_repository = FakeOrderRepository()

    response = await execute_get_profile_summary(
        user_repository=user_repository,
        order_repository=order_repository,
    )

    assert response.user.id == 1
    assert response.user.email == "ivan@example.com"
    assert response.stats.orders_count == 12
    assert response.stats.addresses_count == 2
    assert response.default_address is not None
    assert response.active_order is not None
    assert response.recent_orders[0].order_number == "ORD-100"
    assert order_repository.recent_limit == 5


@pytest.mark.asyncio
async def test_get_profile_summary_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    cached_response = ProfileSummaryResponse(
        user={
            "id": 1,
            "name": "Иван Иванов",
            "phone": "+79990000000",
            "email": "ivan@example.com",
            "role": UserRole.CUSTOMER,
            "is_active": True,
            "is_verified": False,
        },
        stats={"orders_count": 1, "addresses_count": 0},
        default_address=None,
        active_order=None,
        recent_orders=[],
    )
    redis_service.values["profile:summary:1"] = cached_response.model_dump_json()
    user_repository = FakeUserRepository(None)

    response = await execute_get_profile_summary(
        user_repository=user_repository,
        redis_service=redis_service,
    )

    assert response.stats.orders_count == 1
    assert user_repository.requested_user_id is None


@pytest.mark.asyncio
async def test_get_profile_summary_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_summary_with_invalid_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization="Bearer invalid-token", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_summary_with_refresh_token_instead_of_access_token() -> None:
    refresh_token = AuthService().create_refresh_token(user_id=1, role=UserRole.CUSTOMER)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=f"Bearer {refresh_token}", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_summary_user_not_found() -> None:
    with pytest.raises(CurrentUserNotFoundError):
        await execute_get_profile_summary(user_repository=FakeUserRepository(None))


@pytest.mark.asyncio
async def test_get_profile_summary_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        await execute_get_profile_summary(user_repository=FakeUserRepository(build_user(is_active=False)))


@pytest.mark.asyncio
async def test_get_profile_summary_deleted_user() -> None:
    with pytest.raises(InactiveUserError):
        await execute_get_profile_summary(user_repository=FakeUserRepository(build_user(is_deleted=True)))


@pytest.mark.asyncio
async def test_get_profile_summary_uses_current_user_id_only() -> None:
    user_repository = FakeUserRepository(build_user(user_id=7))

    await execute_get_profile_summary(user_repository=user_repository, user_id=7)

    assert user_repository.requested_user_id == 7


@pytest.mark.asyncio
async def test_get_profile_summary_response_does_not_include_password_hash() -> None:
    response = await execute_get_profile_summary(user_repository=FakeUserRepository(build_user()))

    response_data = response.model_dump()
    assert "password_hash" not in response_data
    assert "refresh_token" not in response_data


@pytest.mark.asyncio
async def test_get_profile_summary_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()

    await execute_get_profile_summary(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
    )

    assert "profile:summary:1" in redis_service.values
    assert redis_service.ttls["profile:summary:1"] == settings.profile_summary.cache_ttl_seconds
