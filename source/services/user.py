from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.user import User
from source.errors.auth import CurrentUserNotFoundError, InactiveUserError
from source.schemas.pydantic.user import UserMeResponse
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

    async def _get_user_by_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

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
