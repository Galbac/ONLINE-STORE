from datetime import datetime
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError, AdminAuthRateLimitExceededError, InactiveUserError, InvalidCredentialsError
from source.schemas.pydantic.admin_auth import AdminLoginRequest
from source.services.admin_auth import AdminAuthService, AuditLogService, JwtService, RateLimitService
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


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.created = []

    async def create(self, *, session, user_id: int, token_hash: str, expires_at: datetime):
        self.created.append({"user_id": user_id, "token_hash": token_hash, "expires_at": expires_at})
        return SimpleNamespace(id=len(self.created), user_id=user_id, token_hash=token_hash, expires_at=expires_at)


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


@pytest.mark.asyncio
async def test_admin_login_success_admin() -> None:
    refresh_repository = FakeRefreshTokenRepository()
    audit_repository = FakeAuditLogRepository()

    response = await login(refresh_token_repository=refresh_repository, audit_log_repository=audit_repository)

    assert response.user.role == UserRole.ADMIN
    assert response.user.permissions == ["admin:dashboard:read", "admin:products:manage", "admin:orders:manage"]
    assert response.token_type == "bearer"
    assert response.access_token
    assert response.refresh_token
    assert refresh_repository.created[0]["token_hash"] != response.refresh_token
    assert audit_repository.logs[0]["status"] == "success"


@pytest.mark.asyncio
async def test_admin_login_success_manager() -> None:
    response = await login(user=build_user(role=UserRole.MANAGER))

    assert response.user.role == UserRole.MANAGER
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
