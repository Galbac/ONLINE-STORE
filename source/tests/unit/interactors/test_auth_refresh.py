from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from jose import jwt

from source.config.settings import settings
from source.db.models.admin_audit_log import AdminAuditLog
from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    InvalidRefreshTokenError,
    InvalidRefreshTokenTypeError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenExpiredError,
    RefreshTokenRateLimitExceededError,
    RefreshTokenUserNotFoundError,
)
from source.interactors.auth_refresh import AuthRefreshInteractor
from source.schemas.pydantic.auth import RefreshTokenRequest
from source.services.auth import AuthService


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

    async def execute(self, statement):
        if getattr(statement, "__visit_name__", "") == "update":
            now = datetime.now(UTC)
            for refresh_token in self.refresh_tokens:
                if refresh_token.revoked_at is None:
                    refresh_token.revoked_at = now
            return FakeScalarResult(None)
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)

    def add(self, instance) -> None:
        self.added.append(instance)
        if isinstance(instance, RefreshToken) and instance not in self.refresh_tokens:
            self.refresh_tokens.append(instance)

    async def flush(self) -> None:
        for index, instance in enumerate(self.added, start=1):
            if getattr(instance, "id", None) is None:
                instance.id = index


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


def build_user(*, user_id: int = 1, is_active: bool = True, is_deleted: bool = False) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash="hash",
        role=UserRole.CUSTOMER,
        is_active=is_active,
        is_deleted=is_deleted,
    )
    user.id = user_id
    return user


def build_refresh_token(
    *,
    raw_token: str,
    user_id: int = 1,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> RefreshToken:
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=30),
        revoked_at=revoked_at,
    )
    refresh_token.id = 1
    return refresh_token


async def execute_refresh(
    *,
    auth_service: AuthService,
    session: FakeSession,
    refresh_token: str,
    redis_service: FakeRedisService | None = None,
):
    return await AuthRefreshInteractor().execute(
        session=session,
        auth_service=auth_service,
        redis_service=redis_service or FakeRedisService(),
        data=RefreshTokenRequest(refresh_token=refresh_token),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


@pytest.mark.asyncio
async def test_refresh_success_rotates_refresh_token() -> None:
    auth_service = AuthService()
    old_raw_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)
    old_refresh_token = build_refresh_token(raw_token=old_raw_token)
    session = FakeSession(execute_results=[old_refresh_token, build_user()], refresh_tokens=[old_refresh_token])

    response = await execute_refresh(
        auth_service=auth_service,
        session=session,
        refresh_token=old_raw_token,
    )

    assert response.access_token
    assert response.refresh_token
    assert response.refresh_token != old_raw_token
    assert response.token_type == "bearer"
    assert old_refresh_token.revoked_at is not None
    stored_tokens = [item for item in session.added if isinstance(item, RefreshToken)]
    assert stored_tokens[-1].token_hash == sha256(response.refresh_token.encode("utf-8")).hexdigest()
    assert stored_tokens[-1].token_hash != response.refresh_token


@pytest.mark.asyncio
async def test_refresh_new_tokens_have_expected_token_types() -> None:
    auth_service = AuthService()
    old_raw_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)
    session = FakeSession(
        execute_results=[build_refresh_token(raw_token=old_raw_token), build_user()],
    )

    response = await execute_refresh(
        auth_service=auth_service,
        session=session,
        refresh_token=old_raw_token,
    )

    access_payload = jwt.decode(
        response.access_token,
        settings.auth.jwt_secret_key,
        algorithms=[settings.auth.jwt_algorithm],
    )
    refresh_payload = jwt.decode(
        response.refresh_token,
        settings.auth.jwt_secret_key,
        algorithms=[settings.auth.jwt_algorithm],
    )
    assert access_payload["token_type"] == "access"
    assert refresh_payload["token_type"] == "refresh"
    assert access_payload["jti"]
    assert refresh_payload["jti"]


@pytest.mark.asyncio
async def test_refresh_with_access_token_raises_wrong_type() -> None:
    auth_service = AuthService()
    access_token = auth_service.create_access_token(user_id=1, role=UserRole.CUSTOMER)

    with pytest.raises(InvalidRefreshTokenTypeError):
        await execute_refresh(
            auth_service=auth_service,
            session=FakeSession(),
            refresh_token=access_token,
        )


@pytest.mark.asyncio
async def test_refresh_with_invalid_token() -> None:
    with pytest.raises(InvalidRefreshTokenError):
        await execute_refresh(
            auth_service=AuthService(),
            session=FakeSession(),
            refresh_token="invalid-token",
        )


@pytest.mark.asyncio
async def test_refresh_with_expired_jwt() -> None:
    auth_service = AuthService()
    expired_token = auth_service._create_token(
        user_id=1,
        role=UserRole.CUSTOMER,
        token_type="refresh",
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(RefreshTokenExpiredError):
        await execute_refresh(
            auth_service=auth_service,
            session=FakeSession(),
            refresh_token=expired_token,
        )


@pytest.mark.asyncio
async def test_refresh_with_revoked_token_revokes_all_active_tokens() -> None:
    auth_service = AuthService()
    raw_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)
    revoked_token = build_refresh_token(raw_token=raw_token, revoked_at=datetime.now(UTC))
    active_token = build_refresh_token(raw_token="another-raw-token")
    session = FakeSession(execute_results=[revoked_token], refresh_tokens=[revoked_token, active_token])

    with pytest.raises(RefreshTokenAlreadyRevokedError):
        await execute_refresh(
            auth_service=auth_service,
            session=session,
            refresh_token=raw_token,
        )

    assert active_token.revoked_at is not None
    assert any(isinstance(item, AdminAuditLog) and item.event == "auth_refresh_reuse_detected" for item in session.added)


@pytest.mark.asyncio
async def test_refresh_user_not_found() -> None:
    auth_service = AuthService()
    raw_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)
    session = FakeSession(execute_results=[build_refresh_token(raw_token=raw_token), None])

    with pytest.raises(RefreshTokenUserNotFoundError):
        await execute_refresh(
            auth_service=auth_service,
            session=session,
            refresh_token=raw_token,
        )


@pytest.mark.asyncio
async def test_refresh_inactive_user() -> None:
    auth_service = AuthService()
    raw_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)
    session = FakeSession(execute_results=[build_refresh_token(raw_token=raw_token), build_user(is_active=False)])

    with pytest.raises(InactiveUserError):
        await execute_refresh(
            auth_service=auth_service,
            session=session,
            refresh_token=raw_token,
        )


@pytest.mark.asyncio
async def test_refresh_rate_limit() -> None:
    auth_service = AuthService()
    raw_token = auth_service.create_refresh_token(user_id=1, role=UserRole.CUSTOMER)
    redis_service = FakeRedisService()
    redis_service.values["auth:refresh:rate:user:1"] = str(settings.auth.refresh_rate_limit_per_minute)

    with pytest.raises(RefreshTokenRateLimitExceededError):
        await execute_refresh(
            auth_service=auth_service,
            session=FakeSession(),
            refresh_token=raw_token,
            redis_service=redis_service,
        )
