from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.schemas.pydantic.user import AdminUserListQueryParams, AdminUserListResponse
from source.services.admin_auth import PermissionService
from source.services.admin_user import AdminUserService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds


class FakeUserRepository:
    def __init__(self, users) -> None:
        self.users = users
        self.list_calls = 0
        self.count_calls = 0

    async def admin_get_customers(self, *, session, query: AdminUserListQueryParams):
        self.list_calls += 1
        users = self._filter(query=query)
        users.sort(key=lambda user: user.created_date, reverse=True)
        return users[query.offset : query.offset + query.limit]

    async def admin_count_customers(self, *, session, query: AdminUserListQueryParams) -> int:
        self.count_calls += 1
        return len(self._filter(query=query))

    def _filter(self, *, query: AdminUserListQueryParams):
        users = [user for user in self.users if user.role == UserRole.CUSTOMER]
        if query.q is not None:
            q = query.q.lower()
            users = [
                user
                for user in users
                if q in user.name.lower()
                or q in user.phone.lower()
                or q in (user.email or "").lower()
            ]
        if query.is_active is not None:
            users = [user for user in users if user.is_active is query.is_active]
        if query.is_blocked is not None:
            users = [user for user in users if (not user.is_active) is query.is_blocked]
        if query.is_deleted is not None:
            users = [user for user in users if user.is_deleted is query.is_deleted]
        else:
            users = [user for user in users if user.is_deleted is False]
        return users


class FakeOrderRepository:
    def __init__(self, stats_by_user_id=None) -> None:
        self.stats_by_user_id = stats_by_user_id or {}
        self.user_ids = []

    async def get_user_stats_grouped(self, *, session, user_ids: list[int]):
        self.user_ids = user_ids
        return self.stats_by_user_id


def build_admin(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=100, role=role, is_active=True, is_deleted=False)


def build_user(
    *,
    user_id: int,
    name: str = "Иван Иванов",
    phone: str = "+79990000000",
    email: str | None = "ivan@example.com",
    role=UserRole.CUSTOMER,
    is_active: bool = True,
    is_deleted: bool = False,
):
    return SimpleNamespace(
        id=user_id,
        name=name,
        phone=phone,
        email=email,
        password_hash="secret-hash",
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
        created_date=datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=user_id),
    )


async def get_users(
    *,
    users=None,
    query=None,
    redis_service=None,
    role=UserRole.ADMIN,
    user_repository=None,
    order_repository=None,
):
    return await AdminUserService().get_users(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_admin(role=role),
        query=query or AdminUserListQueryParams(),
        permission_service=PermissionService(),
        user_repository=user_repository or FakeUserRepository(users or []),
        order_repository=order_repository or FakeOrderRepository(),
    )


@pytest.mark.asyncio
async def test_admin_get_users_success() -> None:
    stats = {
        1: SimpleNamespace(orders_count=12, total_spent=Decimal("45000.00")),
    }
    response = await get_users(
        users=[build_user(user_id=1)],
        order_repository=FakeOrderRepository(stats),
    )

    assert response.total == 1
    assert response.page == 1
    assert response.limit == 50
    assert response.pages == 1
    assert response.items[0].id == 1
    assert response.items[0].orders_count == 12
    assert response.items[0].total_spent == Decimal("45000.00")


@pytest.mark.asyncio
async def test_admin_get_users_searches_by_q() -> None:
    response = await get_users(
        users=[
            build_user(user_id=1, name="Иван Иванов"),
            build_user(user_id=2, name="Петр Петров", email="petr@example.com"),
        ],
        query=AdminUserListQueryParams(q="  ПЕТР  "),
    )

    assert response.total == 1
    assert response.items[0].name == "Петр Петров"


@pytest.mark.asyncio
async def test_admin_get_users_filters_by_is_active() -> None:
    response = await get_users(
        users=[
            build_user(user_id=1, is_active=True),
            build_user(user_id=2, is_active=False),
        ],
        query=AdminUserListQueryParams(is_active=False),
    )

    assert response.total == 1
    assert response.items[0].id == 2


@pytest.mark.asyncio
async def test_admin_get_users_filters_by_is_blocked() -> None:
    response = await get_users(
        users=[
            build_user(user_id=1, is_active=True),
            build_user(user_id=2, is_active=False),
        ],
        query=AdminUserListQueryParams(is_blocked=True),
    )

    assert response.total == 1
    assert response.items[0].id == 2
    assert response.items[0].is_blocked is True


@pytest.mark.asyncio
async def test_admin_get_users_password_hash_not_returned() -> None:
    response = await get_users(users=[build_user(user_id=1)])

    dumped = response.model_dump()
    assert "password_hash" not in dumped["items"][0]


@pytest.mark.asyncio
async def test_admin_get_users_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_users(
            users=[build_user(user_id=1)],
            role=UserRole.CONTENT_MANAGER,
        )


@pytest.mark.asyncio
async def test_admin_get_users_response_is_cached() -> None:
    redis_service = FakeRedisService()
    query = AdminUserListQueryParams(q="Иван")

    await get_users(redis_service=redis_service, users=[build_user(user_id=1)], query=query)

    normalized_query = query.model_copy(update={"q": normalize_search_query(query.q)})
    cache_key = f"admin:users:list:{build_query_hash(normalized_query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.admin_users.list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_get_users_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    query = AdminUserListQueryParams()
    cached_response = AdminUserListResponse.build(
        items=[],
        total=0,
        page=query.page,
        limit=query.limit,
    )
    redis_service.values[f"admin:users:list:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()
    user_repository = FakeUserRepository([build_user(user_id=1)])

    response = await get_users(redis_service=redis_service, user_repository=user_repository, query=query)

    assert response == cached_response
    assert user_repository.list_calls == 0
