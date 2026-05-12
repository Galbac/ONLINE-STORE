from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import json
from secrets import token_urlsafe
from urllib.parse import urlencode

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    InvalidCredentialsError,
    PasswordResetRateLimitExceededError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    MessageResponse,
    RegisterAuthResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserShortResponse,
)
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.redis import RedisService


PASSWORD_RESET_SUCCESS_MESSAGE = "Если пользователь найден, инструкция по восстановлению пароля будет отправлена"


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
            "iat": now,
            "exp": now + expires_delta,
        }
        return jwt.encode(
            claims=payload,
            key=settings.auth.jwt_secret_key,
            algorithm=settings.auth.jwt_algorithm,
        )

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

    def _normalize_login(self, login: str) -> str:
        normalized_login = login.strip()
        return normalized_login.lower() if "@" in normalized_login else normalized_login

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

    def _build_password_reset_link(self, reset_token: str) -> str:
        return f"{settings.password_reset.frontend_url}?{urlencode({'token': reset_token})}"

    def _decode_redis_value(self, value: str | bytes) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

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
