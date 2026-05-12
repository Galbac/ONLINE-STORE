from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import CurrentUserResponse
from source.services.auth import AuthService
from source.services.redis import RedisService


class AuthMeInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService,
        user_id: int,
    ) -> CurrentUserResponse:
        return await auth_service.get_current_user_profile(
            session=session,
            redis_service=redis_service,
            user_id=user_id,
        )
