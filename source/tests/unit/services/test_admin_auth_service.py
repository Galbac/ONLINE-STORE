from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminAuthRateLimitExceededError,
    AdminCurrentUserNotFoundError,
    InactiveUserError,
    InvalidCredentialsError,
    RefreshTokenAlreadyRevokedError,
)
from source.schemas.pydantic.admin_auth import AdminLoginRequest, AdminLogoutRequest, AdminMeResponse
from source.services.admin_auth import AdminAuthService, AuditLogService, JwtBlacklistService, JwtService, PermissionService, RateLimitService
from source.services.admin_auth_cache import AdminAuthCacheService
from source.services.auth import AuthService


DEFAULT_USER = object()


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        self.values[key] = str(int(self.values.get(key, "0")) + 1)
        return int(self.values[key])

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds


class FakeUserRepository:
    def __init__(self, user=None) -> None:
        self.user = user
        self.requested_email = None
        self.requested_phone = None

    async def get_by_email(self, *, session, email: str):
        self.requested_email = email
        return self.user if self.user and self.user.email == email else None

    async def get_by_phone(self, *, session, phone: str):
        self.requested_phone = phone
        return self.user if self.user and self.user.phone == phone else None

    async def get_by_id(self, *, session, user_id: int):
        return self.user if self.user and self.user.id == user_id else None


class FakeRefreshTokenRepository:
    def __init__(self, token=None) -> None:
        self.token = token
        self.created = []
        self.revoked = []

    async def create(self, *, session, user_id: int, token_hash: str, expires_at: datetime):
        self.created.append({"user_id": user_id, "token_hash": token_hash, "expires_at": expires_at})
        return SimpleNamespace(id=len(self.created), user_id=user_id, token_hash=token_hash, expires_at=expires_at)

    async def get_by_hash(self, *, session, token_hash: str):
        return self.token if self.token and self.token.token_hash == token_hash else None

    async def revoke(self, *, session, refresh_token, revoked_at: datetime):
        refresh_token.revoked_at = revoked_at
        self.revoked.append(refresh_token)
        return refresh_token


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)


def build_user(*, role=UserRole.ADMIN, is_active: bool = True, is_deleted: bool = False, password: str = "StrongPassword123"):
    return SimpleNamespace(
        id=1,
        name="Администратор",
        email="admin@example.com",
        phone="+79990000000",
        role=role,
        password_hash=AuthService().hash_password(password),
        is_active=is_active,
        is_deleted=is_deleted,
    )


async def login(
    *,
    user=DEFAULT_USER,
    data=None,
    redis_service=None,
    refresh_token_repository=None,
    audit_log_repository=None,
):
    repository_user = build_user() if user is DEFAULT_USER else user
    return await AdminAuthService().login(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        data=data or AdminLoginRequest(login="admin@example.com", password="StrongPassword123"),
        user_repository=FakeUserRepository(repository_user),
        refresh_token_repository=refresh_token_repository or FakeRefreshTokenRepository(),
        jwt_service=JwtService(),
        rate_limit_service=RateLimitService(),
        audit_log_service=AuditLogService(),
        audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


async def logout(
    *,
    user=None,
    refresh_token: str = "refresh-token",
    refresh_token_user_id: int = 1,
    revoked_at=None,
    redis_service=None,
    token_payload=None,
    refresh_token_repository=None,
    audit_log_repository=None,
):
    user = user or build_user()
    token = SimpleNamespace(
        id=1,
        user_id=refresh_token_user_id,
        token_hash=sha256(refresh_token.encode("utf-8")).hexdigest(),
        revoked_at=revoked_at,
    )
    repository = refresh_token_repository or FakeRefreshTokenRepository(token=token)
    return await AdminAuthService().logout(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user,
        data=AdminLogoutRequest(refresh_token=refresh_token),
        token_payload=token_payload or build_access_payload(user_id=user.id, role=user.role),
        refresh_token_repository=repository,
        jwt_blacklist_service=JwtBlacklistService(),
        audit_log_service=AuditLogService(),
        audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


async def get_me(*, user=DEFAULT_USER, redis_service=None, token_payload=None):
    repository_user = build_user() if user is DEFAULT_USER else user
    return await AdminAuthService().get_me(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user_id=1,
        token_payload=token_payload or build_access_payload(),
        user_repository=FakeUserRepository(repository_user),
        admin_auth_cache_service=AdminAuthCacheService(),
        permission_service=PermissionService(),
    )


def build_access_payload(*, user_id: int = 1, role=UserRole.ADMIN, jti: str = "access-jti") -> dict:
    return {
        "user_id": user_id,
        "role": role.value,
        "token_type": "access",
        "jti": jti,
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
    }


@pytest.mark.asyncio
async def test_admin_login_success_admin() -> None:
    refresh_repository = FakeRefreshTokenRepository()
    audit_repository = FakeAuditLogRepository()

    response = await login(refresh_token_repository=refresh_repository, audit_log_repository=audit_repository)

    assert response.user.role == UserRole.ADMIN
    assert response.user.permissions == [
        "admin:dashboard:read",
        "admin:dashboard:sales:read",
        "admin:categories:read",
        "admin:products:read",
        "admin:products:create",
        "admin:products:update",
        "admin:products:delete",
        "admin:products:stock:update",
        "admin:products:manage",
        "admin:orders:manage",
    ]
    assert response.token_type == "bearer"
    assert response.access_token
    assert response.refresh_token
    assert refresh_repository.created[0]["token_hash"] != response.refresh_token
    assert audit_repository.logs[0]["status"] == "success"


@pytest.mark.asyncio
async def test_admin_login_success_manager() -> None:
    response = await login(user=build_user(role=UserRole.MANAGER))

    assert response.user.role == UserRole.MANAGER
    assert "admin:products:create" in response.user.permissions
    assert "admin:products:update" in response.user.permissions
    assert "admin:products:delete" in response.user.permissions
    assert "admin:products:stock:update" in response.user.permissions
    assert "admin:orders:manage" in response.user.permissions


@pytest.mark.asyncio
async def test_admin_login_customer_role_error() -> None:
    audit_repository = FakeAuditLogRepository()

    with pytest.raises(AdminAuthAccessDeniedError):
        await login(user=build_user(role=UserRole.CUSTOMER), audit_log_repository=audit_repository)

    assert audit_repository.logs[0]["status"] == "forbidden"


@pytest.mark.asyncio
async def test_admin_login_invalid_password_error() -> None:
    redis_service = FakeRedisService()
    audit_repository = FakeAuditLogRepository()

    with pytest.raises(InvalidCredentialsError):
        await login(
            data=AdminLoginRequest(login="admin@example.com", password="WrongPassword"),
            redis_service=redis_service,
            audit_log_repository=audit_repository,
        )

    assert redis_service.values["admin:auth:failed:admin@example.com"] == "1"
    assert redis_service.ttls["admin:auth:failed:admin@example.com"] == settings.admin_auth.login_failed_window_seconds
    assert audit_repository.logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_admin_login_nonexistent_user_error() -> None:
    audit_repository = FakeAuditLogRepository()

    with pytest.raises(InvalidCredentialsError):
        await login(user=None, audit_log_repository=audit_repository)

    assert audit_repository.logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_admin_login_blocked_user_error() -> None:
    audit_repository = FakeAuditLogRepository()

    with pytest.raises(InactiveUserError):
        await login(user=build_user(is_active=False), audit_log_repository=audit_repository)

    assert audit_repository.logs[0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_admin_login_rate_limit_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.admin_auth, "login_failed_limit", 1)
    redis_service = FakeRedisService()
    redis_service.values["admin:auth:failed:admin@example.com"] = "1"

    with pytest.raises(AdminAuthRateLimitExceededError):
        await login(redis_service=redis_service)


@pytest.mark.asyncio
async def test_admin_login_password_hash_not_returned() -> None:
    response = await login()

    assert "password_hash" not in response.model_dump()["user"]


@pytest.mark.asyncio
async def test_admin_logout_success() -> None:
    audit_repository = FakeAuditLogRepository()
    refresh_repository = FakeRefreshTokenRepository(
        token=SimpleNamespace(
            id=1,
            user_id=1,
            token_hash=sha256("refresh-token".encode("utf-8")).hexdigest(),
            revoked_at=None,
        ),
    )

    response = await logout(refresh_token_repository=refresh_repository, audit_log_repository=audit_repository)

    assert response.message == "Вы успешно вышли из админ-панели"
    assert refresh_repository.revoked[0].revoked_at is not None
    assert audit_repository.logs[0]["event"] == "admin_logout"
    assert audit_repository.logs[0]["status"] == "success"


@pytest.mark.asyncio
async def test_admin_logout_foreign_refresh_token_error() -> None:
    audit_repository = FakeAuditLogRepository()

    with pytest.raises(AdminAuthAccessDeniedError):
        await logout(refresh_token_user_id=2, audit_log_repository=audit_repository)

    assert audit_repository.logs[0]["status"] == "forbidden"


@pytest.mark.asyncio
async def test_admin_logout_already_revoked_token_error() -> None:
    audit_repository = FakeAuditLogRepository()

    with pytest.raises(RefreshTokenAlreadyRevokedError):
        await logout(revoked_at=datetime.now(UTC), audit_log_repository=audit_repository)

    assert audit_repository.logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_admin_logout_adds_access_token_to_blacklist(monkeypatch) -> None:
    monkeypatch.setattr(settings.change_password, "jwt_access_blacklist_enabled", True)
    redis_service = FakeRedisService()

    await logout(redis_service=redis_service, token_payload=build_access_payload(jti="logout-jti"))

    assert redis_service.values["auth:blacklist:access:logout-jti"] == "revoked"
    assert redis_service.ttls["auth:blacklist:access:logout-jti"] > 0


@pytest.mark.asyncio
async def test_admin_logout_refresh_token_not_found_error() -> None:
    from source.errors.auth import RefreshTokenNotFoundError

    with pytest.raises(RefreshTokenNotFoundError):
        await logout(refresh_token_repository=FakeRefreshTokenRepository(token=None))


@pytest.mark.asyncio
async def test_admin_get_me_success() -> None:
    response = await get_me()

    assert response.id == 1
    assert response.role == UserRole.ADMIN
    assert response.is_active is True
    assert "admin:dashboard:read" in response.permissions


@pytest.mark.asyncio
async def test_admin_get_me_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminMeResponse(
        id=1,
        name="Администратор",
        email="admin@example.com",
        phone="+79990000000",
        role=UserRole.ADMIN,
        permissions=["admin:dashboard:read"],
        is_active=True,
    )
    redis_service.values["admin:auth:me:1"] = cached_response.model_dump_json()

    response = await get_me(user=None, redis_service=redis_service)

    assert response == cached_response


@pytest.mark.asyncio
async def test_admin_get_me_customer_role_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_me(user=build_user(role=UserRole.CUSTOMER))


@pytest.mark.asyncio
async def test_admin_get_me_blocked_user_error() -> None:
    with pytest.raises(InactiveUserError):
        await get_me(user=build_user(is_active=False))


@pytest.mark.asyncio
async def test_admin_get_me_password_hash_not_returned() -> None:
    response = await get_me()

    assert "password_hash" not in response.model_dump()


@pytest.mark.asyncio
async def test_admin_get_me_response_is_cached() -> None:
    redis_service = FakeRedisService()

    await get_me(redis_service=redis_service)

    assert "admin:auth:me:1" in redis_service.values
    assert redis_service.ttls["admin:auth:me:1"] == settings.admin_auth.me_cache_ttl_seconds
