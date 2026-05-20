from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminStaffInvalidRoleError,
    AdminStaffNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.admin_staff import AdminStaffCreateRequest, AdminStaffListQueryParams, AdminStaffListResponse
from source.services.admin_auth import PermissionService
from source.services.admin_staff import AdminStaffService
from source.services.admin_staff_cache import AdminStaffCacheService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted_patterns = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)


class FakeUserRepository:
    def __init__(self, users) -> None:
        self.users = users
        self.list_calls = 0
        self.count_calls = 0

    async def admin_get_staff_list(self, *, session, query: AdminStaffListQueryParams):
        self.list_calls += 1
        users = self._filter(query=query)
        users.sort(key=lambda user: user.created_date, reverse=True)
        return users[query.offset : query.offset + query.limit]

    async def admin_count_staff(self, *, session, query: AdminStaffListQueryParams) -> int:
        self.count_calls += 1
        return len(self._filter(query=query))

    async def get_by_phone(self, *, session, phone: str):
        return next((user for user in self.users if user.phone == phone), None)

    async def get_by_email(self, *, session, email: str):
        return next((user for user in self.users if user.email == email), None)

    async def get_by_id(self, *, session, user_id: int):
        return next((user for user in self.users if user.id == user_id), None)

    async def create(self, *, session, **data):
        user = build_user(user_id=len(self.users) + 1, **data)
        self.users.append(user)
        return user

    def _filter(self, *, query: AdminStaffListQueryParams):
        users = [user for user in self.users if user.role != UserRole.CUSTOMER]
        if query.q is not None:
            q = query.q.lower()
            users = [
                user
                for user in users
                if q in user.name.lower()
                or q in user.phone.lower()
                or q in (user.email or "").lower()
            ]
        if query.role is not None:
            users = [user for user in users if user.role == query.role]
        if query.is_active is not None:
            users = [user for user in users if user.is_active is query.is_active]
        if query.is_blocked is not None:
            users = [user for user in users if user.is_blocked is query.is_blocked]
        return users


def build_current_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=100, role=role, is_active=True, is_deleted=False, is_blocked=False)


def build_user(
    *,
    user_id: int,
    role=UserRole.MANAGER,
    name: str = "Менеджер",
    email: str | None = "manager@example.com",
    phone: str = "+79990000000",
    password_hash: str = "secret-hash",
    is_active: bool = True,
    is_blocked: bool = False,
):
    return SimpleNamespace(
        id=user_id,
        name=name,
        email=email,
        phone=phone,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
        is_deleted=False,
        is_blocked=is_blocked,
        created_date=datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=user_id),
    )


async def get_staff(*, users=None, query=None, redis_service=None, role=UserRole.ADMIN, repository=None):
    return await AdminStaffService().get_staff_list(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_current_user(role=role),
        query=query or AdminStaffListQueryParams(),
        permission_service=PermissionService(),
        user_repository=repository or FakeUserRepository(users or []),
        admin_staff_cache_service=AdminStaffCacheService(),
    )


async def get_staff_detail(*, users=None, staff_id: int = 1, redis_service=None, role=UserRole.ADMIN, repository=None):
    return await AdminStaffService().get_staff_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_current_user(role=role),
        staff_id=staff_id,
        permission_service=PermissionService(),
        user_repository=repository or FakeUserRepository(users or []),
        admin_staff_cache_service=AdminStaffCacheService(),
    )


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


class FakePasswordService:
    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"


async def create_staff(
    *,
    users=None,
    data: AdminStaffCreateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    repository = repository or FakeUserRepository(users or [])
    response = await AdminStaffService().create_staff(
        session=None,
        redis_service=redis_service,
        user=build_current_user(role=role),
        data=data or AdminStaffCreateRequest(
            name="Менеджер Иван",
            email="manager@example.com",
            phone="+79991112233",
            password="StrongPassword123",
            role=UserRole.MANAGER,
            is_active=True,
        ),
        commiter=commiter,
        permission_service=PermissionService(),
        user_repository=repository,
        password_service=FakePasswordService(),
        admin_audit_log_repository=audit_log_repository,
        admin_staff_cache_service=AdminStaffCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
    )


@pytest.mark.asyncio
async def test_admin_get_staff_success() -> None:
    response = await get_staff(users=[build_user(user_id=1)])

    assert response.total == 1
    assert response.page == 1
    assert response.limit == 50
    assert response.pages == 1
    assert response.items[0].role == UserRole.MANAGER


@pytest.mark.asyncio
async def test_admin_get_staff_excludes_customers() -> None:
    response = await get_staff(
        users=[
            build_user(user_id=1, role=UserRole.MANAGER),
            build_user(user_id=2, role=UserRole.CUSTOMER),
        ],
    )

    assert response.total == 1
    assert response.items[0].role == UserRole.MANAGER


@pytest.mark.asyncio
async def test_admin_get_staff_filters_by_role() -> None:
    response = await get_staff(
        users=[
            build_user(user_id=1, role=UserRole.MANAGER),
            build_user(user_id=2, role=UserRole.COURIER),
        ],
        query=AdminStaffListQueryParams(role=UserRole.COURIER),
    )

    assert response.total == 1
    assert response.items[0].role == UserRole.COURIER


@pytest.mark.asyncio
async def test_admin_get_staff_filters_by_is_active() -> None:
    response = await get_staff(
        users=[
            build_user(user_id=1, is_active=True),
            build_user(user_id=2, is_active=False),
        ],
        query=AdminStaffListQueryParams(is_active=False),
    )

    assert response.total == 1
    assert response.items[0].is_active is False


@pytest.mark.asyncio
async def test_admin_get_staff_searches_by_q() -> None:
    response = await get_staff(
        users=[
            build_user(user_id=1, name="Менеджер"),
            build_user(user_id=2, name="Курьер", email="courier@example.com"),
        ],
        query=AdminStaffListQueryParams(q="  courier  "),
    )

    assert response.total == 1
    assert response.items[0].email == "courier@example.com"


@pytest.mark.asyncio
async def test_admin_get_staff_pagination() -> None:
    response = await get_staff(
        users=[
            build_user(user_id=1),
            build_user(user_id=2),
            build_user(user_id=3),
        ],
        query=AdminStaffListQueryParams(page=2, limit=2),
    )

    assert response.total == 3
    assert response.pages == 2
    assert len(response.items) == 1
    assert response.items[0].id == 1


@pytest.mark.asyncio
async def test_admin_get_staff_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_staff(users=[build_user(user_id=1)], role=UserRole.PICKER)


@pytest.mark.asyncio
async def test_admin_get_staff_password_hash_not_returned() -> None:
    response = await get_staff(users=[build_user(user_id=1)])

    assert "password_hash" not in response.model_dump()["items"][0]


@pytest.mark.asyncio
async def test_admin_get_staff_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    query = AdminStaffListQueryParams(q="Менеджер")
    normalized_query = query.model_copy(update={"q": normalize_search_query(query.q)})
    cached_response = AdminStaffListResponse.build(items=[], total=0, page=query.page, limit=query.limit)
    redis_service.values[
        f"admin:staff:list:{build_query_hash(normalized_query.model_dump())}"
    ] = cached_response.model_dump_json()
    repository = FakeUserRepository([build_user(user_id=1)])

    response = await get_staff(redis_service=redis_service, repository=repository, query=query)

    assert response == cached_response
    assert repository.list_calls == 0


@pytest.mark.asyncio
async def test_admin_get_staff_response_is_cached() -> None:
    redis_service = FakeRedisService()
    query = AdminStaffListQueryParams(role=UserRole.MANAGER)

    await get_staff(redis_service=redis_service, users=[build_user(user_id=1)], query=query)

    cache_key = f"admin:staff:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.admin_staff.list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_get_staff_detail_success() -> None:
    response = await get_staff_detail(users=[build_user(user_id=1, role=UserRole.MANAGER)])

    assert response.id == 1
    assert response.role == UserRole.MANAGER
    assert "admin:orders:read" in response.permissions
    assert response.is_blocked is False


@pytest.mark.asyncio
async def test_admin_get_staff_detail_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = await get_staff_detail(users=[build_user(user_id=1)])
    redis_service.values["admin:staff:detail:1"] = cached_response.model_dump_json()
    repository = FakeUserRepository([])

    response = await get_staff_detail(redis_service=redis_service, repository=repository)

    assert response == cached_response
    assert repository.list_calls == 0


@pytest.mark.asyncio
async def test_admin_get_staff_detail_not_found_error() -> None:
    with pytest.raises(AdminStaffNotFoundError):
        await get_staff_detail(users=[], staff_id=404)


@pytest.mark.asyncio
async def test_admin_get_staff_detail_customer_not_found_error() -> None:
    with pytest.raises(AdminStaffNotFoundError):
        await get_staff_detail(users=[build_user(user_id=1, role=UserRole.CUSTOMER)])


@pytest.mark.asyncio
async def test_admin_get_staff_detail_password_hash_not_returned() -> None:
    response = await get_staff_detail(users=[build_user(user_id=1)])

    dumped = response.model_dump()
    assert "password_hash" not in dumped
    assert "refresh_tokens" not in dumped


@pytest.mark.asyncio
async def test_admin_get_staff_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_staff_detail(users=[build_user(user_id=1)], role=UserRole.PICKER)


@pytest.mark.asyncio
async def test_admin_create_staff_manager_success() -> None:
    result = await create_staff()

    assert result.response.id == 1
    assert result.response.role == UserRole.MANAGER
    assert result.response.email == "manager@example.com"
    assert result.commiter.committed is True
    assert result.repository.users[0].password_hash == "hashed:StrongPassword123"


@pytest.mark.asyncio
async def test_admin_create_staff_picker_success() -> None:
    result = await create_staff(
        data=AdminStaffCreateRequest(
            name="Сборщик Петр",
            email="picker@example.com",
            phone="+79991112234",
            password="StrongPassword123",
            role=UserRole.PICKER,
            is_active=True,
        ),
    )

    assert result.response.role == UserRole.PICKER


@pytest.mark.asyncio
async def test_admin_create_staff_email_already_exists_error() -> None:
    with pytest.raises(UserEmailAlreadyExistsError):
        await create_staff(users=[build_user(user_id=1, email="manager@example.com")])


@pytest.mark.asyncio
async def test_admin_create_staff_phone_already_exists_error() -> None:
    with pytest.raises(UserPhoneAlreadyExistsError):
        await create_staff(users=[build_user(user_id=1, phone="+79991112233")])


def test_admin_create_staff_weak_password_error() -> None:
    with pytest.raises(ValidationError):
        AdminStaffCreateRequest(
            name="Менеджер Иван",
            email="manager@example.com",
            phone="+79991112233",
            password="weakpassword",
            role=UserRole.MANAGER,
        )


@pytest.mark.asyncio
async def test_admin_create_staff_invalid_role_error() -> None:
    with pytest.raises(AdminStaffInvalidRoleError):
        await create_staff(
            data=AdminStaffCreateRequest(
                name="Клиент Иван",
                email="customer@example.com",
                phone="+79991112235",
                password="StrongPassword123",
                role=UserRole.CUSTOMER,
            ),
        )


@pytest.mark.asyncio
async def test_admin_create_staff_password_hash_not_returned() -> None:
    result = await create_staff()

    assert "password_hash" not in result.response.model_dump()


@pytest.mark.asyncio
async def test_admin_create_staff_audit_log_created() -> None:
    result = await create_staff()

    assert result.audit_log_repository.logs[0]["event"] == "admin_staff_create"
    assert result.audit_log_repository.logs[0]["details"] == {
        "target_user_id": 1,
        "role": "manager",
    }


@pytest.mark.asyncio
async def test_admin_create_staff_invalidates_cache() -> None:
    result = await create_staff()

    assert "admin:staff:*" in result.redis_service.deleted_patterns
    assert "admin:roles:*" in result.redis_service.deleted_patterns
