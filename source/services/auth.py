from datetime import UTC, datetime, timedelta

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.auth import AuthResponse, UserRegisterRequest


class AuthService:
    def __init__(self) -> None:
        self._password_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
        )

    def hash_password(self, password: str) -> str:
        return self._password_context.hash(password)

    async def register_user(
        self,
        *,
        session: AsyncSession,
        data: UserRegisterRequest,
    ) -> AuthResponse:
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

        return AuthResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            access_token=self.create_access_token(
                user_id=user.id,
                role=user.role,
            ),
            refresh_token=self.create_refresh_token(
                user_id=user.id,
                role=user.role,
            ),
        )

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
