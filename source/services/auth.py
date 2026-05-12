from datetime import UTC, datetime, timedelta
from hashlib import sha256

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
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.auth import (
    AuthResponse,
    RegisterAuthResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserShortResponse,
)


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
        normalized_login = login.strip()
        condition = User.email == normalized_login.lower() if "@" in normalized_login else User.phone == normalized_login
        result = await session.execute(select(User).where(condition))
        return result.scalar_one_or_none()

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
