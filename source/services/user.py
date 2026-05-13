from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.user import User
from source.errors.auth import (
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.user import UserMeResponse, UserMeUpdateRequest
from source.services.auth_cache import AuthCacheService
from source.services.redis import RedisService
from source.services.user_cache import UserCacheService


class UserService:
    async def get_current_user_profile(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user_cache_service: UserCacheService,
        user_id: int,
    ) -> UserMeResponse:
        cached_user = await user_cache_service.get_user_me_cache(
            redis_service=redis_service,
            user_id=user_id,
        )
        if cached_user is not None:
            return cached_user

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active:
            raise InactiveUserError

        response = self._build_user_me_response(user)
        await user_cache_service.set_user_me_cache(
            redis_service=redis_service,
            user_id=user.id,
            response=response,
            ttl_seconds=settings.user_me.cache_ttl_seconds,
        )
        return response

    async def update_current_user_profile(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user_cache_service: UserCacheService,
        auth_cache_service: AuthCacheService,
        user_id: int,
        data: UserMeUpdateRequest,
    ) -> UserMeResponse:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise EmptyUserProfileUpdateError

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active:
            raise InactiveUserError

        phone = update_data.get("phone")
        if phone is not None and phone != user.phone:
            await self._ensure_phone_is_unique(
                session=session,
                phone=phone,
                current_user_id=user.id,
            )
            user.phone = phone

        email = update_data.get("email")
        if "email" in update_data and email != user.email:
            if email is not None:
                await self._ensure_email_is_unique(
                    session=session,
                    email=email,
                    current_user_id=user.id,
                )
            user.email = email

        name = update_data.get("name")
        if name is not None:
            user.name = name

        user.updated_date = datetime.now(settings.tz)
        session.add(user)
        await session.flush()
        await session.refresh(user)

        await user_cache_service.delete_user_me_cache(
            redis_service=redis_service,
            user_id=user.id,
        )
        await auth_cache_service.delete_current_user_cache(
            redis_service=redis_service,
            user_id=user.id,
        )

        return self._build_user_me_response(user)

    async def _get_user_by_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _ensure_phone_is_unique(
        self,
        *,
        session: AsyncSession,
        phone: str,
        current_user_id: int,
    ) -> None:
        result = await session.execute(
            select(User.id).where(
                User.phone == phone,
                User.id != current_user_id,
            ),
        )
        if result.scalar_one_or_none() is not None:
            raise UserPhoneAlreadyExistsError

    async def _ensure_email_is_unique(
        self,
        *,
        session: AsyncSession,
        email: str,
        current_user_id: int,
    ) -> None:
        result = await session.execute(
            select(User.id).where(
                User.email == email,
                User.id != current_user_id,
            ),
        )
        if result.scalar_one_or_none() is not None:
            raise UserEmailAlreadyExistsError

    def _build_user_me_response(self, user: User) -> UserMeResponse:
        return UserMeResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            is_verified=False,
            created_at=user.created_date,
            updated_at=user.updated_date,
        )
