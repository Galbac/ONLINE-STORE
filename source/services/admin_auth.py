from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from jose import jwt

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminAuthRateLimitExceededError,
    AdminCurrentUserNotFoundError,
    InactiveUserError,
    InvalidCredentialsError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
)
from source.schemas.pydantic.admin_auth import (
    AdminAuthResponse,
    AdminLoginRequest,
    AdminLogoutRequest,
    AdminMeResponse,
    AdminUserResponse,
    MessageResponse,
)
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
    UserRole.ADMIN: [
        "admin:dashboard:read",
        "admin:dashboard:sales:read",
        "admin:categories:read",
        "admin:categories:create",
        "admin:categories:update",
        "admin:categories:delete",
        "admin:products:read",
        "admin:products:create",
        "admin:products:update",
        "admin:products:delete",
        "admin:products:stock:update",
        "admin:products:manage",
        "admin:discounts:read",
        "admin:orders:read",
        "admin:orders:manage",
        "admin:orders:cancel",
        "admin:orders:confirm",
        "admin:orders:print",
        "admin:orders:sync_1c",
        "admin:orders:update",
        "admin:orders:update_status",
        "admin:users:read",
        "admin:users:update",
        "admin:users:block",
        "admin:staff:read",
        "admin:staff:create",
        "admin:staff:update",
        "admin:staff:delete",
        "admin:staff:change_role",
        "admin:roles:read",
    ],
    UserRole.MANAGER: [
        "admin:dashboard:read",
        "admin:dashboard:sales:read",
        "admin:categories:read",
        "admin:categories:create",
        "admin:categories:update",
        "admin:categories:delete",
        "admin:products:read",
        "admin:products:create",
        "admin:products:update",
        "admin:products:delete",
        "admin:products:stock:update",
        "admin:products:manage",
        "admin:orders:read",
        "admin:orders:manage",
        "admin:orders:cancel",
        "admin:orders:confirm",
        "admin:orders:print",
        "admin:orders:sync_1c",
        "admin:orders:update",
        "admin:orders:update_status",
        "admin:users:read",
        "admin:users:update",
        "admin:users:block",
        "admin:staff:read",
        "admin:staff:create",
        "admin:staff:update",
    ],
    UserRole.CONTENT_MANAGER: [
        "admin:dashboard:read",
        "admin:categories:read",
        "admin:categories:create",
        "admin:categories:update",
        "admin:categories:delete",
        "admin:products:read",
        "admin:products:manage",
    ],
    UserRole.PICKER: ["admin:dashboard:read", "admin:orders:pick", "admin:orders:print"],
    UserRole.COURIER: ["admin:dashboard:read", "admin:orders:deliver"],
}

ROLE_LEVELS = {
    UserRole.COURIER: 10,
    UserRole.PICKER: 20,
    UserRole.CONTENT_MANAGER: 30,
    UserRole.MANAGER: 80,
    UserRole.ADMIN: 100,
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


class JwtBlacklistService:
    async def blacklist_access_token(self, *, redis_service: RedisService, token_payload: dict) -> None:
        if not settings.change_password.jwt_access_blacklist_enabled:
            return

        jti = token_payload.get("jti")
        exp = token_payload.get("exp")
        if not jti or not isinstance(exp, int):
            return

        ttl_seconds = exp - int(datetime.now(UTC).timestamp())
        if ttl_seconds > 0:
            await redis_service.set(f"auth:blacklist:access:{jti}", "revoked", ttl_seconds=ttl_seconds)


class AuditLogService:
    async def log_action(
        self,
        *,
        session,
        audit_log_repository,
        user_id: int,
        login: str,
        event: str,
        status: str = "success",
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        await audit_log_repository.create(
            session=session,
            user_id=user_id,
            login=login,
            event=event,
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
        )

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

    async def log_admin_logout(
        self,
        *,
        session,
        audit_log_repository,
        user_id: int,
        login: str,
        status: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        await audit_log_repository.create(
            session=session,
            user_id=user_id,
            login=login,
            event="admin_logout",
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
        )


class PermissionService:
    def get_user_permissions(self, *, role: UserRole) -> list[str]:
        return ADMIN_PERMISSIONS_BY_ROLE.get(role, [])

    def validate_role_assignable(self, *, actor_role: UserRole, target_role: UserRole) -> bool:
        actor_level = ROLE_LEVELS.get(actor_role, 0)
        target_level = ROLE_LEVELS.get(target_role, 0)
        return target_level > 0 and target_level <= actor_level


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

    async def logout(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminLogoutRequest,
        token_payload: dict,
        refresh_token_repository,
        jwt_blacklist_service: JwtBlacklistService,
        audit_log_service: AuditLogService,
        audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> MessageResponse:
        if token_payload.get("token_type") != "access":
            raise InvalidCredentialsError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError

        login = user.email or user.phone
        token_hash = sha256(data.refresh_token.encode("utf-8")).hexdigest()
        refresh_token = await refresh_token_repository.get_by_hash(session=session, token_hash=token_hash)
        if refresh_token is None:
            await audit_log_service.log_admin_logout(
                session=session,
                audit_log_repository=audit_log_repository,
                user_id=user.id,
                login=login,
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_not_found"},
            )
            raise RefreshTokenNotFoundError
        if refresh_token.user_id != user.id:
            await audit_log_service.log_admin_logout(
                session=session,
                audit_log_repository=audit_log_repository,
                user_id=user.id,
                login=login,
                status="forbidden",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_owner_mismatch"},
            )
            raise AdminAuthAccessDeniedError
        if refresh_token.revoked_at is not None:
            await audit_log_service.log_admin_logout(
                session=session,
                audit_log_repository=audit_log_repository,
                user_id=user.id,
                login=login,
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_revoked"},
            )
            raise RefreshTokenAlreadyRevokedError

        await refresh_token_repository.revoke(
            session=session,
            refresh_token=refresh_token,
            revoked_at=datetime.now(UTC),
        )
        await jwt_blacklist_service.blacklist_access_token(
            redis_service=redis_service,
            token_payload=token_payload,
        )
        await audit_log_service.log_admin_logout(
            session=session,
            audit_log_repository=audit_log_repository,
            user_id=user.id,
            login=login,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return MessageResponse(message="Вы успешно вышли из админ-панели")

    async def get_me(
        self,
        *,
        session,
        redis_service: RedisService,
        user_id: int,
        token_payload: dict,
        user_repository,
        admin_auth_cache_service,
        permission_service: PermissionService,
    ) -> AdminMeResponse:
        if token_payload.get("token_type") != "access":
            raise InvalidCredentialsError

        cached_user = await admin_auth_cache_service.get_me(
            redis_service=redis_service,
            user_id=user_id,
        )
        if cached_user is not None:
            return cached_user

        user = await user_repository.get_by_id(session=session, user_id=user_id)
        if user is None:
            raise AdminCurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError

        response = AdminMeResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            permissions=permission_service.get_user_permissions(role=user.role),
            is_active=user.is_active,
        )
        await admin_auth_cache_service.set_me(
            redis_service=redis_service,
            user_id=user.id,
            response=response,
            ttl_seconds=settings.admin_auth.me_cache_ttl_seconds,
        )
        return response

    def get_permissions_for_role(self, role: UserRole) -> list[str]:
        return ADMIN_PERMISSIONS_BY_ROLE.get(role, [])

    async def _get_user(self, *, user_repository, session, login: str):
        if "@" in login:
            return await user_repository.get_by_email(session=session, email=login.lower())
        return await user_repository.get_by_phone(session=session, phone=login)
