from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from jose import jwt

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError, AdminAuthRateLimitExceededError, InactiveUserError, InvalidCredentialsError
from source.schemas.pydantic.admin_auth import AdminAuthResponse, AdminLoginRequest, AdminUserResponse
from source.services.auth import AuthService
from source.services.redis import RedisService


STAFF_ROLES = {
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.CONTENT_MANAGER,
    UserRole.PICKER,
    UserRole.COURIER,
}

ADMIN_PERMISSIONS_BY_ROLE = {
    UserRole.ADMIN: ["admin:dashboard:read", "admin:products:manage", "admin:orders:manage"],
    UserRole.MANAGER: ["admin:dashboard:read", "admin:products:manage", "admin:orders:manage"],
    UserRole.CONTENT_MANAGER: ["admin:dashboard:read", "admin:products:manage"],
    UserRole.PICKER: ["admin:dashboard:read", "admin:orders:pick"],
    UserRole.COURIER: ["admin:dashboard:read", "admin:orders:deliver"],
}


class JwtService:
    def create_access_token(self, *, user_id: int, role: UserRole, permissions: list[str]) -> str:
        return self._create_token(
            user_id=user_id,
            role=role,
            permissions=permissions,
            token_type="access",
            expires_delta=timedelta(minutes=settings.admin_auth.access_expire_minutes),
        )

    def create_refresh_token(self, *, user_id: int, role: UserRole, permissions: list[str]) -> str:
        return self._create_token(
            user_id=user_id,
            role=role,
            permissions=permissions,
            token_type="refresh",
            expires_delta=timedelta(days=settings.admin_auth.refresh_expire_days),
        )

    def _create_token(
        self,
        *,
        user_id: int,
        role: UserRole,
        permissions: list[str],
        token_type: str,
        expires_delta: timedelta,
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "user_id": user_id,
            "role": role.value,
            "permissions": permissions,
            "token_type": token_type,
            "jti": uuid4().hex,
            "iat": now,
            "exp": now + expires_delta,
        }
        return jwt.encode(payload, settings.auth.jwt_secret_key, algorithm=settings.auth.jwt_algorithm)


class RateLimitService:
    async def check_admin_login_limit(self, *, redis_service: RedisService, login: str) -> None:
        value = await redis_service.get(self._key(login=login))
        if value is None:
            return
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if int(value) >= settings.admin_auth.login_failed_limit:
            raise AdminAuthRateLimitExceededError

    async def increment_admin_login_failed(self, *, redis_service: RedisService, login: str) -> None:
        key = self._key(login=login)
        failed_count = await redis_service.incr(key)
        if failed_count == 1:
            await redis_service.expire(key, settings.admin_auth.login_failed_window_seconds)
        if failed_count > settings.admin_auth.login_failed_limit:
            raise AdminAuthRateLimitExceededError

    def _key(self, *, login: str) -> str:
        return f"admin:auth:failed:{login}"


class AuditLogService:
    async def log_admin_login(
        self,
        *,
        session,
        audit_log_repository,
        login: str,
        status: str,
        user_id: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        await audit_log_repository.create(
            session=session,
            user_id=user_id,
            login=login,
            event="admin_login",
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
        )


class AdminAuthService:
    def __init__(self) -> None:
        self._auth_service = AuthService()

    async def login(
        self,
        *,
        session,
        redis_service: RedisService,
        data: AdminLoginRequest,
        user_repository,
        refresh_token_repository,
        jwt_service: JwtService,
        rate_limit_service: RateLimitService,
        audit_log_service: AuditLogService,
        audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuthResponse:
        await rate_limit_service.check_admin_login_limit(redis_service=redis_service, login=data.login)

        user = await self._get_user(user_repository=user_repository, session=session, login=data.login)
        if user is None:
            await audit_log_service.log_admin_login(
                session=session,
                audit_log_repository=audit_log_repository,
                login=data.login,
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_credentials"},
            )
            raise InvalidCredentialsError
        if not user.is_active or user.is_deleted:
            await audit_log_service.log_admin_login(
                session=session,
                audit_log_repository=audit_log_repository,
                login=data.login,
                status="blocked",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            await audit_log_service.log_admin_login(
                session=session,
                audit_log_repository=audit_log_repository,
                login=data.login,
                status="forbidden",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AdminAuthAccessDeniedError
        if not self._auth_service.verify_password(data.password, user.password_hash):
            await audit_log_service.log_admin_login(
                session=session,
                audit_log_repository=audit_log_repository,
                login=data.login,
                status="failed",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_credentials"},
            )
            await rate_limit_service.increment_admin_login_failed(redis_service=redis_service, login=data.login)
            raise InvalidCredentialsError

        permissions = self.get_permissions_for_role(user.role)
        access_token = jwt_service.create_access_token(user_id=user.id, role=user.role, permissions=permissions)
        refresh_token = jwt_service.create_refresh_token(user_id=user.id, role=user.role, permissions=permissions)
        await refresh_token_repository.create(
            session=session,
            user_id=user.id,
            token_hash=sha256(refresh_token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(days=settings.admin_auth.refresh_expire_days),
        )
        await audit_log_service.log_admin_login(
            session=session,
            audit_log_repository=audit_log_repository,
            login=data.login,
            status="success",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return AdminAuthResponse(
            user=AdminUserResponse(
                id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                permissions=permissions,
            ),
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def get_permissions_for_role(self, role: UserRole) -> list[str]:
        return ADMIN_PERMISSIONS_BY_ROLE.get(role, [])

    async def _get_user(self, *, user_repository, session, login: str):
        if "@" in login:
            return await user_repository.get_by_email(session=session, email=login.lower())
        return await user_repository.get_by_phone(session=session, phone=login)
