from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import json
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import uuid4

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.admin_audit_log import AdminAuditLog
from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    ChangePasswordRateLimitExceededError,
    CurrentUserNotFoundError,
    InactiveUserError,
    InvalidCurrentPasswordError,
    InvalidPasswordResetTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidRefreshTokenTypeError,
    NewPasswordSameAsOldError,
    PasswordResetRateLimitExceededError,
    PasswordResetUserNotFoundError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenExpiredError,
    RefreshTokenNotFoundError,
    RefreshTokenRateLimitExceededError,
    RefreshTokenUserNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.auth import (
    AuthResponse,
    ChangePasswordRequest,
    CurrentUserResponse,
    ForgotPasswordRequest,
    MessageResponse,
    RegisterAuthResponse,
    ResetPasswordRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserShortResponse,
)
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.redis import RedisService


PASSWORD_RESET_SUCCESS_MESSAGE = "Если пользователь найден, инструкция по восстановлению пароля будет отправлена"
RESET_PASSWORD_SUCCESS_MESSAGE = "Пароль успешно изменён"


class AuthService:
    def __init__(self) -> None:
        self._password_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
        )

    def hash_password(self, password: str) -> str:
        return self._password_context.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self._password_context.verify(password, password_hash)

    async def register_user(
        self,
        *,
        session: AsyncSession,
        data: UserRegisterRequest,
    ) -> RegisterAuthResponse:
        await self._ensure_phone_is_unique(session=session, phone=data.phone)
        if data.email is not None:
            await self._ensure_email_is_unique(session=session, email=str(data.email))

        user = User(
            name=data.name,
            phone=data.phone,
            email=str(data.email) if data.email is not None else None,
            password_hash=self.hash_password(data.password),
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)

        access_token = self.create_access_token(
            user_id=user.id,
            role=user.role,
        )
        refresh_token = self.create_refresh_token(
            user_id=user.id,
            role=user.role,
        )
        await self._store_refresh_token(
            session=session,
            user_id=user.id,
            refresh_token=refresh_token,
        )

        return RegisterAuthResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def login_user(
        self,
        *,
        session: AsyncSession,
        data: UserLoginRequest,
    ) -> AuthResponse:
        user = await self._get_user_by_login(session=session, login=data.login)
        if user is None:
            raise InvalidCredentialsError
        if not user.is_active:
            raise InactiveUserError
        if not self.verify_password(data.password, user.password_hash):
            raise InvalidCredentialsError

        access_token = self.create_access_token(user_id=user.id, role=user.role)
        refresh_token = self.create_refresh_token(user_id=user.id, role=user.role)
        await self._store_refresh_token(
            session=session,
            user_id=user.id,
            refresh_token=refresh_token,
        )

        return AuthResponse(
            user=UserShortResponse.model_validate(user),
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def logout_user(
        self,
        *,
        session: AsyncSession,
        user: User,
        refresh_token: str,
    ) -> None:
        token = await self._get_refresh_token(
            session=session,
            refresh_token=refresh_token,
        )
        if token is None or token.user_id != user.id:
            raise RefreshTokenNotFoundError
        if token.revoked_at is not None:
            raise RefreshTokenAlreadyRevokedError

        token.revoked_at = datetime.now(UTC)
        session.add(token)
        await session.flush()

    async def refresh_tokens(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        data: RefreshTokenRequest,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenPairResponse:
        payload = self._decode_refresh_token(data.refresh_token)
        user_id = payload.get("user_id")
        jti = payload.get("jti")
        if user_id is None or not jti:
            raise InvalidRefreshTokenError

        try:
            user_id = int(user_id)
        except (TypeError, ValueError) as error:
            raise InvalidRefreshTokenError from error
        await self._check_refresh_rate_limit(redis_service=redis_service, user_id=user_id)

        token = await self._get_refresh_token(session=session, refresh_token=data.refresh_token)
        if token is None:
            await self._log_auth_security_event(
                session=session,
                user_id=None,
                event="auth_refresh",
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_not_found", "jti": jti},
            )
            raise RefreshTokenNotFoundError

        now = datetime.now(UTC)
        if token.revoked_at is not None:
            await self._log_auth_security_event(
                session=session,
                user_id=user_id,
                event="auth_refresh_reuse_detected",
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_revoked", "jti": jti},
            )
            if settings.auth.refresh_reuse_detection_enabled:
                await self._revoke_active_refresh_tokens(session=session, user_id=token.user_id)
                await session.flush()
            raise RefreshTokenAlreadyRevokedError

        if token.expires_at <= now:
            await self._log_auth_security_event(
                session=session,
                user_id=None,
                event="auth_refresh",
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_expired", "jti": jti},
            )
            raise RefreshTokenExpiredError

        if token.user_id != user_id:
            await self._log_auth_security_event(
                session=session,
                user_id=None,
                event="auth_refresh",
                status="forbidden",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "refresh_token_owner_mismatch", "jti": jti},
            )
            raise InvalidRefreshTokenError

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise RefreshTokenUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        access_token = self.create_access_token(user_id=user.id, role=user.role)
        refresh_token = data.refresh_token
        if settings.auth.refresh_rotation_enabled:
            token.revoked_at = now
            session.add(token)
            refresh_token = self.create_refresh_token(user_id=user.id, role=user.role)
            await self._store_refresh_token(
                session=session,
                user_id=user.id,
                refresh_token=refresh_token,
            )
        await self._log_auth_security_event(
            session=session,
            user_id=user.id,
            event="auth_refresh",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={"rotation": settings.auth.refresh_rotation_enabled},
        )
        await session.flush()

        return TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def forgot_password(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        data: ForgotPasswordRequest,
        ip_address: str,
        user_agent: str | None,
    ) -> MessageResponse:
        user = await self._get_user_by_login(session=session, login=data.login)
        if user is None or not user.is_active:
            return MessageResponse(message=PASSWORD_RESET_SUCCESS_MESSAGE)

        normalized_login = self._normalize_login(data.login)
        await self._check_password_reset_rate_limit(
            redis_service=redis_service,
            key=f"password_reset:rate:login:{normalized_login}",
            limit=settings.password_reset.rate_limit_by_login,
        )
        await self._check_password_reset_rate_limit(
            redis_service=redis_service,
            key=f"password_reset:rate:ip:{ip_address}",
            limit=settings.password_reset.rate_limit_by_ip,
        )

        user_key = f"password_reset:user:{user.id}"
        old_token_hash = await redis_service.get(user_key)
        if old_token_hash is not None:
            old_token_hash = self._decode_redis_value(old_token_hash)
            await redis_service.delete(f"password_reset:token:{old_token_hash}")
            await redis_service.delete(user_key)

        reset_token = token_urlsafe(48)
        token_hash = self.hash_password_reset_token(reset_token)
        token_key = f"password_reset:token:{token_hash}"
        created_at = datetime.now(UTC).isoformat()
        token_payload = json.dumps(
            {
                "user_id": user.id,
                "created_at": created_at,
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )

        ttl_seconds = settings.password_reset.token_ttl_seconds
        await redis_service.set(token_key, token_payload)
        await redis_service.expire(token_key, ttl_seconds)
        await redis_service.set(user_key, token_hash)
        await redis_service.expire(user_key, ttl_seconds)

        reset_link = self._build_password_reset_link(reset_token)
        if user.email:
            await email_service.send_password_reset_email(
                email=user.email,
                reset_link=reset_link,
            )
        else:
            await telegram_service.notify_admin_password_reset_issue(
                user_id=user.id,
                login=normalized_login,
            )

        return MessageResponse(message=PASSWORD_RESET_SUCCESS_MESSAGE)

    def hash_password_reset_token(self, reset_token: str) -> str:
        return hmac.new(
            settings.password_reset.token_secret.encode("utf-8"),
            reset_token.encode("utf-8"),
            sha256,
        ).hexdigest()

    async def reset_password(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        data: ResetPasswordRequest,
    ) -> MessageResponse:
        token_hash = self.hash_password_reset_token(data.token)
        token_key = f"password_reset:token:{token_hash}"
        token_payload = await redis_service.get(token_key)
        if token_payload is None:
            raise InvalidPasswordResetTokenError

        payload = self._load_password_reset_payload(token_payload)
        user_id = payload.get("user_id")
        if not isinstance(user_id, int):
            raise InvalidPasswordResetTokenError

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise PasswordResetUserNotFoundError
        if not user.is_active:
            raise InactiveUserError
        if self.verify_password(data.new_password, user.password_hash):
            raise NewPasswordSameAsOldError

        user.password_hash = self.hash_password(data.new_password)
        session.add(user)
        await self._revoke_active_refresh_tokens(session=session, user_id=user.id)
        await session.flush()

        await redis_service.delete(token_key)
        await redis_service.delete(f"password_reset:user:{user.id}")
        await self.invalidate_current_user_cache(redis_service=redis_service, user_id=user.id)

        return MessageResponse(message=RESET_PASSWORD_SUCCESS_MESSAGE)

    async def change_password(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user: User,
        data: ChangePasswordRequest,
        ip_address: str,
        access_token: str | None,
    ) -> MessageResponse:
        if not user.is_active:
            raise InactiveUserError

        await self._check_change_password_rate_limit(
            redis_service=redis_service,
            key=f"auth:change_password:rate:user:{user.id}",
            limit=settings.change_password.rate_limit_by_user,
            window_seconds=settings.change_password.rate_limit_window_seconds,
        )
        await self._check_change_password_rate_limit(
            redis_service=redis_service,
            key=f"auth:change_password:rate:ip:{ip_address}",
            limit=settings.change_password.rate_limit_by_ip,
            window_seconds=settings.change_password.rate_limit_window_seconds,
        )

        failed_key = f"auth:change_password:failed:user:{user.id}"
        failed_count = await self._get_redis_int(redis_service=redis_service, key=failed_key)
        if failed_count >= settings.change_password.failed_limit:
            raise ChangePasswordRateLimitExceededError

        if not self.verify_password(data.current_password, user.password_hash):
            failed_count = await redis_service.incr(failed_key)
            if failed_count == 1:
                await redis_service.expire(failed_key, settings.change_password.failed_window_seconds)
            if failed_count >= settings.change_password.failed_limit:
                raise ChangePasswordRateLimitExceededError
            raise InvalidCurrentPasswordError

        if self.verify_password(data.new_password, user.password_hash):
            raise NewPasswordSameAsOldError

        user.password_hash = self.hash_password(data.new_password)
        session.add(user)
        await self._revoke_active_refresh_tokens(session=session, user_id=user.id)
        await session.flush()

        await redis_service.delete(failed_key)
        await self._delete_password_reset_tokens(redis_service=redis_service, user_id=user.id)
        await self.invalidate_current_user_cache(redis_service=redis_service, user_id=user.id)
        await self._blacklist_access_token_if_enabled(
            redis_service=redis_service,
            access_token=access_token,
        )

        return MessageResponse(message=RESET_PASSWORD_SUCCESS_MESSAGE)

    async def get_current_user_profile(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user_id: int,
    ) -> CurrentUserResponse:
        cache_key = f"auth:me:user:{user_id}"
        cached_user = await redis_service.get(cache_key)
        if cached_user is not None:
            return CurrentUserResponse.model_validate_json(
                self._decode_redis_value(cached_user),
            )

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active:
            raise InactiveUserError

        response = self._build_current_user_response(user)
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.auth_me.cache_ttl_seconds,
        )
        return response

    async def invalidate_current_user_cache(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(f"auth:me:user:{user_id}")
        await redis_service.delete(f"users:me:{user_id}")

    def create_access_token(self, *, user_id: int, role: UserRole) -> str:
        return self._create_token(
            user_id=user_id,
            role=role,
            token_type="access",
            expires_delta=timedelta(minutes=settings.auth.access_token_expire_minutes),
        )

    def create_refresh_token(self, *, user_id: int, role: UserRole) -> str:
        return self._create_token(
            user_id=user_id,
            role=role,
            token_type="refresh",
            expires_delta=timedelta(minutes=settings.auth.refresh_token_expire_minutes),
        )

    def _create_token(
        self,
        *,
        user_id: int,
        role: UserRole,
        token_type: str,
        expires_delta: timedelta,
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "user_id": user_id,
            "role": role.value,
            "token_type": token_type,
            "jti": uuid4().hex,
            "iat": now,
            "exp": now + expires_delta,
        }
        return jwt.encode(
            claims=payload,
            key=settings.auth.jwt_secret_key,
            algorithm=settings.auth.jwt_algorithm,
        )

    def _decode_refresh_token(self, refresh_token: str) -> dict:
        try:
            payload = jwt.decode(
                token=refresh_token,
                key=settings.auth.jwt_secret_key,
                algorithms=[settings.auth.jwt_algorithm],
            )
        except ExpiredSignatureError as error:
            raise RefreshTokenExpiredError from error
        except JWTError as error:
            raise InvalidRefreshTokenError from error

        if payload.get("token_type") != "refresh":
            raise InvalidRefreshTokenTypeError
        return payload

    async def _ensure_phone_is_unique(
        self,
        *,
        session: AsyncSession,
        phone: str,
    ) -> None:
        result = await session.execute(select(User.id).where(User.phone == phone))
        if result.scalar_one_or_none() is not None:
            raise UserPhoneAlreadyExistsError

    async def _ensure_email_is_unique(
        self,
        *,
        session: AsyncSession,
        email: str,
    ) -> None:
        result = await session.execute(select(User.id).where(User.email == email))
        if result.scalar_one_or_none() is not None:
            raise UserEmailAlreadyExistsError

    async def _get_user_by_login(
        self,
        *,
        session: AsyncSession,
        login: str,
    ) -> User | None:
        normalized_login = self._normalize_login(login)
        condition = User.email == normalized_login.lower() if "@" in normalized_login else User.phone == normalized_login
        result = await session.execute(select(User).where(condition))
        return result.scalar_one_or_none()

    async def _get_user_by_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    def _normalize_login(self, login: str) -> str:
        normalized_login = login.strip()
        return normalized_login.lower() if "@" in normalized_login else normalized_login

    def _build_current_user_response(self, user: User) -> CurrentUserResponse:
        return CurrentUserResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role=user.role,
            permissions=self._get_permissions_for_role(user.role),
            is_active=user.is_active,
            is_verified=False,
            created_at=user.created_date,
        )

    def _get_permissions_for_role(self, role: UserRole) -> list[str]:
        if role == UserRole.CUSTOMER:
            return ["profile:read", "orders:read", "orders:create"]
        return []

    async def _check_password_reset_rate_limit(
        self,
        *,
        redis_service: RedisService,
        key: str,
        limit: int,
    ) -> None:
        requests_count = await redis_service.incr(key)
        if requests_count == 1:
            await redis_service.expire(key, settings.password_reset.rate_limit_window_seconds)
        if requests_count > limit:
            raise PasswordResetRateLimitExceededError

    async def _check_change_password_rate_limit(
        self,
        *,
        redis_service: RedisService,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        requests_count = await redis_service.incr(key)
        if requests_count == 1:
            await redis_service.expire(key, window_seconds)
        if requests_count > limit:
            raise ChangePasswordRateLimitExceededError

    async def _check_refresh_rate_limit(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        key = f"auth:refresh:rate:user:{user_id}"
        requests_count = await redis_service.incr(key)
        if requests_count == 1:
            await redis_service.expire(key, 60)
        if requests_count > settings.auth.refresh_rate_limit_per_minute:
            raise RefreshTokenRateLimitExceededError

    def _build_password_reset_link(self, reset_token: str) -> str:
        return f"{settings.password_reset.frontend_url}?{urlencode({'token': reset_token})}"

    def _decode_redis_value(self, value: str | bytes) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def _load_password_reset_payload(self, value: str | bytes) -> dict:
        try:
            payload = json.loads(self._decode_redis_value(value))
        except json.JSONDecodeError as error:
            raise InvalidPasswordResetTokenError from error
        if not isinstance(payload, dict):
            raise InvalidPasswordResetTokenError
        return payload

    async def _revoke_active_refresh_tokens(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> None:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC)),
        )

    async def _delete_password_reset_tokens(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        user_key = f"password_reset:user:{user_id}"
        token_hash = await redis_service.get(user_key)
        if token_hash is not None:
            token_hash = self._decode_redis_value(token_hash)
            await redis_service.delete(f"password_reset:token:{token_hash}")
        await redis_service.delete(user_key)

    async def _blacklist_access_token_if_enabled(
        self,
        *,
        redis_service: RedisService,
        access_token: str | None,
    ) -> None:
        if not settings.change_password.jwt_access_blacklist_enabled or not access_token:
            return
        try:
            payload = jwt.decode(
                token=access_token,
                key=settings.auth.jwt_secret_key,
                algorithms=[settings.auth.jwt_algorithm],
            )
        except JWTError:
            return

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not isinstance(exp, int):
            return

        ttl_seconds = exp - int(datetime.now(UTC).timestamp())
        if ttl_seconds > 0:
            await redis_service.set(
                f"auth:blacklist:access:{jti}",
                "revoked",
                ttl_seconds=ttl_seconds,
            )

    async def _log_auth_security_event(
        self,
        *,
        session: AsyncSession,
        user_id: int | None,
        event: str,
        status: str,
        ip_address: str | None,
        user_agent: str | None,
        details: dict | None = None,
    ) -> None:
        session.add(
            AdminAuditLog(
                user_id=user_id,
                login=str(user_id) if user_id is not None else "unknown",
                event=event,
                status=status,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details or {},
            ),
        )

    async def _get_redis_int(
        self,
        *,
        redis_service: RedisService,
        key: str,
    ) -> int:
        value = await redis_service.get(key)
        if value is None:
            return 0
        return int(self._decode_redis_value(value))

    async def _store_refresh_token(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        refresh_token: str,
    ) -> None:
        session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=sha256(refresh_token.encode("utf-8")).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(minutes=settings.auth.refresh_token_expire_minutes),
            ),
        )
        await session.flush()

    async def _get_refresh_token(
        self,
        *,
        session: AsyncSession,
        refresh_token: str,
    ) -> RefreshToken | None:
        token_hash = sha256(refresh_token.encode("utf-8")).hexdigest()
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash),
        )
        return result.scalar_one_or_none()
