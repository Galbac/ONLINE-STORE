from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import RegisterAuthResponse, UserRegisterRequest
from source.services.auth import AuthService
from source.services.redis import RedisService


class AuthRegisterInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService | None = None,
        data: UserRegisterRequest,
    ) -> RegisterAuthResponse:
        return await auth_service.register_user(
            session=session,
            data=data,
            redis_service=redis_service,
        )
