from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from pydantic import ValidationError

from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminUserAlreadyBlockedError,
    AdminUserNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.user import (
    AdminUserBlockRequest,
    AdminUserDetailResponse,
    AdminUserListQueryParams,
    AdminUserListResponse,
    AdminUserUpdateRequest,
)
from source.services.admin_auth import PermissionService
from source.services.admin_user import AdminUserService
from source.services.refresh_token import RefreshTokenService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted = []
        self.deleted_patterns = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)


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

    async def get_by_id(self, *, session, user_id: int):
        return next((user for user in self.users if user.id == user_id), None)

    async def get_by_phone(self, *, session, phone: str):
        return next((user for user in self.users if user.phone == phone), None)

    async def get_by_email(self, *, session, email: str):
        return next((user for user in self.users if user.email == email), None)

    async def update(self, *, session, user):
        return user

    async def block(self, *, session, user, blocked_at: datetime, blocked_by: int, block_reason: str):
        user.is_blocked = True
        user.blocked_at = blocked_at
        user.blocked_by = blocked_by
        user.block_reason = block_reason
        user.updated_date = blocked_at
        return user

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
            users = [user for user in users if user.is_blocked is query.is_blocked]
        if query.is_deleted is not None:
            users = [user for user in users if user.is_deleted is query.is_deleted]
        else:
            users = [user for user in users if user.is_deleted is False]
        return users


class FakeOrderRepository:
    def __init__(self, stats_by_user_id=None) -> None:
        self.stats_by_user_id = stats_by_user_id or {}
        self.user_ids = []
        self.recent_orders = []

    async def get_user_stats_grouped(self, *, session, user_ids: list[int]):
        self.user_ids = user_ids
        return self.stats_by_user_id

    async def get_user_stats(self, *, session, user_id: int):
        return self.stats_by_user_id.get(
            user_id,
            SimpleNamespace(orders_count=0, total_spent=Decimal("0.00")),
        )

    async def get_recent_by_user_id(self, *, session, user_id: int, limit: int = 5):
        return self.recent_orders[:limit]


class FakeAddressRepository:
    def __init__(self, addresses=None) -> None:
        self.addresses = addresses or []

    async def get_by_user_id(
        self,
        *,
        session,
        user_id: int,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        return self.addresses[offset : offset + limit]


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(**data)


class FakeUserCacheService:
    async def delete_user_me_cache(self, *, redis_service, user_id: int) -> None:
        await redis_service.delete(f"users:me:{user_id}")


class FakeAuthCacheService:
    async def delete_current_user_cache(self, *, redis_service, user_id: int) -> None:
        await redis_service.delete(f"auth:me:user:{user_id}")


class FakeProfileCacheService:
    async def delete_summary(self, *, redis_service, user_id: int) -> None:
        await redis_service.delete(f"profile:summary:{user_id}")


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.revoked_user_ids = []

    async def revoke_all_by_user_id(self, *, session, user_id: int, revoked_at: datetime) -> int:
        self.revoked_user_ids.append(user_id)
        return 3


def build_admin(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=100, role=role, is_active=True, is_deleted=False, is_blocked=False)


def build_user(
    *,
    user_id: int,
    name: str = "Иван Иванов",
    phone: str = "+79990000000",
    email: str | None = "ivan@example.com",
    role=UserRole.CUSTOMER,
    is_active: bool = True,
    is_deleted: bool = False,
    is_blocked: bool = False,
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
        is_blocked=is_blocked,
        blocked_at=None,
        blocked_by=None,
        block_reason=None,
        created_date=datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=user_id),
        updated_date=datetime(2026, 5, 12, 10, 30, 0),
    )


def build_address(*, address_id: int = 10):
    return SimpleNamespace(
        id=address_id,
        title="Дом",
        city="Москва",
        street="Тверская",
        house="1",
        building=None,
        apartment="10",
        entrance=None,
        floor=None,
        intercom=None,
        comment=None,
        is_default=True,
        created_at=datetime(2026, 5, 12, 10, 0, 0),
    )


def build_order(*, order_id: int = 100):
    return SimpleNamespace(
        id=order_id,
        order_number="ORD-000100",
        status="completed",
        payment_method="online",
        payment_status="paid",
        delivery_type="delivery",
        final_price=Decimal("1500.00"),
        items_count=3,
        created_at=datetime(2026, 5, 13, 10, 0, 0),
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


async def get_user_detail(
    *,
    users=None,
    user_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    user_repository=None,
    address_repository=None,
    order_repository=None,
):
    return await AdminUserService().get_user_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_admin(role=role),
        user_id=user_id,
        permission_service=PermissionService(),
        user_repository=user_repository or FakeUserRepository(users or []),
        address_repository=address_repository or FakeAddressRepository(),
        order_repository=order_repository or FakeOrderRepository(),
    )


async def update_user(
    *,
    users=None,
    user_id: int = 1,
    data: AdminUserUpdateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    user_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    response = await AdminUserService().update_user(
        session=None,
        redis_service=redis_service,
        user=build_admin(role=role),
        user_id=user_id,
        data=data or AdminUserUpdateRequest(name="Иван Петров"),
        commiter=commiter,
        permission_service=PermissionService(),
        user_repository=user_repository or FakeUserRepository(users or []),
        admin_audit_log_repository=audit_log_repository,
        user_cache_service=FakeUserCacheService(),
        auth_cache_service=FakeAuthCacheService(),
        profile_cache_service=FakeProfileCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
    )


async def block_user(
    *,
    users=None,
    user_id: int = 1,
    data: AdminUserBlockRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    user_repository=None,
    refresh_token_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    refresh_token_repository = refresh_token_repository or FakeRefreshTokenRepository()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    response = await AdminUserService().block_user(
        session=None,
        redis_service=redis_service,
        user=build_admin(role=role),
        user_id=user_id,
        data=data or AdminUserBlockRequest(reason="Подозрительная активность", revoke_sessions=True),
        commiter=commiter,
        permission_service=PermissionService(),
        user_repository=user_repository or FakeUserRepository(users or []),
        refresh_token_repository=refresh_token_repository,
        refresh_token_service=RefreshTokenService(),
        admin_audit_log_repository=audit_log_repository,
        user_cache_service=FakeUserCacheService(),
        auth_cache_service=FakeAuthCacheService(),
        profile_cache_service=FakeProfileCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        refresh_token_repository=refresh_token_repository,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
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
            build_user(user_id=1, is_blocked=False),
            build_user(user_id=2, is_blocked=True),
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


@pytest.mark.asyncio
async def test_admin_get_user_detail_success() -> None:
    order_repository = FakeOrderRepository(
        {1: SimpleNamespace(orders_count=12, total_spent=Decimal("45000.00"))},
    )
    order_repository.recent_orders = [build_order()]

    response = await get_user_detail(
        users=[build_user(user_id=1)],
        address_repository=FakeAddressRepository([build_address()]),
        order_repository=order_repository,
    )

    assert response.id == 1
    assert response.orders_count == 12
    assert response.total_spent == Decimal("45000.00")
    assert response.addresses[0].city == "Москва"
    assert response.recent_orders[0].order_number == "ORD-000100"


@pytest.mark.asyncio
async def test_admin_get_user_detail_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminUserDetailResponse(
        id=1,
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        is_active=True,
        is_blocked=False,
        is_deleted=False,
        orders_count=0,
        total_spent=Decimal("0.00"),
        addresses=[],
        recent_orders=[],
        created_at=datetime(2026, 5, 12, 10, 0, 0),
    )
    redis_service.values["admin:users:detail:1"] = cached_response.model_dump_json()

    response = await get_user_detail(redis_service=redis_service, users=[])

    assert response == cached_response


@pytest.mark.asyncio
async def test_admin_get_user_detail_not_found_error() -> None:
    with pytest.raises(AdminUserNotFoundError):
        await get_user_detail(users=[], user_id=404)


@pytest.mark.asyncio
async def test_admin_get_user_detail_password_hash_not_returned() -> None:
    response = await get_user_detail(users=[build_user(user_id=1)])

    dumped = response.model_dump()
    assert "password_hash" not in dumped
    assert "refresh_tokens" not in dumped


@pytest.mark.asyncio
async def test_admin_get_user_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_user_detail(
            users=[build_user(user_id=1)],
            role=UserRole.CONTENT_MANAGER,
        )


@pytest.mark.asyncio
async def test_admin_get_user_detail_response_is_cached() -> None:
    redis_service = FakeRedisService()

    await get_user_detail(redis_service=redis_service, users=[build_user(user_id=1)])

    assert "admin:users:detail:1" in redis_service.values
    assert redis_service.ttls["admin:users:detail:1"] == settings.admin_users.detail_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_update_user_success() -> None:
    user = build_user(user_id=1)

    result = await update_user(
        users=[user],
        data=AdminUserUpdateRequest(
            name="Иван Петров",
            phone="+79991112233",
            email="ivan.petrov@example.com",
            is_active=True,
        ),
    )

    assert result.response.id == 1
    assert result.response.name == "Иван Петров"
    assert result.response.phone == "+79991112233"
    assert result.response.email == "ivan.petrov@example.com"
    assert result.commiter.committed is True
    assert result.audit_log_repository.logs[0]["event"] == "admin_user_update"


@pytest.mark.asyncio
async def test_admin_update_user_phone_already_exists_error() -> None:
    with pytest.raises(UserPhoneAlreadyExistsError):
        await update_user(
            users=[
                build_user(user_id=1, phone="+79990000000"),
                build_user(user_id=2, phone="+79991112233"),
            ],
            data=AdminUserUpdateRequest(phone="+79991112233"),
        )


@pytest.mark.asyncio
async def test_admin_update_user_email_already_exists_error() -> None:
    with pytest.raises(UserEmailAlreadyExistsError):
        await update_user(
            users=[
                build_user(user_id=1, email="ivan@example.com"),
                build_user(user_id=2, email="petr@example.com"),
            ],
            data=AdminUserUpdateRequest(email="petr@example.com"),
        )


def test_admin_update_user_role_is_forbidden() -> None:
    with pytest.raises(ValidationError):
        AdminUserUpdateRequest.model_validate({"role": "admin"})


def test_admin_update_user_password_hash_is_forbidden() -> None:
    with pytest.raises(ValidationError):
        AdminUserUpdateRequest.model_validate({"password_hash": "new-hash"})


@pytest.mark.asyncio
async def test_admin_update_user_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await update_user(
            users=[build_user(user_id=1)],
            role=UserRole.CONTENT_MANAGER,
        )


@pytest.mark.asyncio
async def test_admin_update_user_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    result = await update_user(redis_service=redis_service, users=[build_user(user_id=1)])

    assert "admin:users:*" in result.redis_service.deleted_patterns
    assert "users:me:1" in result.redis_service.deleted
    assert "auth:me:user:1" in result.redis_service.deleted
    assert "profile:summary:1" in result.redis_service.deleted


@pytest.mark.asyncio
async def test_admin_block_user_success() -> None:
    user = build_user(user_id=1)

    result = await block_user(users=[user])

    assert result.response.message == "Пользователь заблокирован"
    assert result.response.user_id == 1
    assert result.response.is_blocked is True
    assert user.is_blocked is True
    assert user.blocked_by == 100
    assert user.block_reason == "Подозрительная активность"
    assert result.audit_log_repository.logs[0]["event"] == "admin_user_block"
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_block_user_already_blocked_error() -> None:
    with pytest.raises(AdminUserAlreadyBlockedError):
        await block_user(users=[build_user(user_id=1, is_blocked=True)])


@pytest.mark.asyncio
async def test_admin_block_user_not_found_error() -> None:
    with pytest.raises(AdminUserNotFoundError):
        await block_user(users=[], user_id=404)


@pytest.mark.asyncio
async def test_admin_block_user_revokes_refresh_tokens() -> None:
    refresh_token_repository = FakeRefreshTokenRepository()

    await block_user(
        users=[build_user(user_id=1)],
        refresh_token_repository=refresh_token_repository,
        data=AdminUserBlockRequest(reason="Подозрительная активность", revoke_sessions=True),
    )

    assert refresh_token_repository.revoked_user_ids == [1]


@pytest.mark.asyncio
async def test_admin_block_user_does_not_revoke_refresh_tokens_when_disabled() -> None:
    refresh_token_repository = FakeRefreshTokenRepository()

    await block_user(
        users=[build_user(user_id=1)],
        refresh_token_repository=refresh_token_repository,
        data=AdminUserBlockRequest(reason="Подозрительная активность", revoke_sessions=False),
    )

    assert refresh_token_repository.revoked_user_ids == []


@pytest.mark.asyncio
async def test_admin_block_user_invalidates_cache() -> None:
    result = await block_user(users=[build_user(user_id=1)])

    assert "admin:users:*" in result.redis_service.deleted_patterns
    assert "users:me:1" in result.redis_service.deleted
    assert "auth:me:user:1" in result.redis_service.deleted
    assert "profile:summary:1" in result.redis_service.deleted
