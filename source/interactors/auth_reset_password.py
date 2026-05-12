from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import MessageResponse, ResetPasswordRequest
from source.services.auth import AuthService
from source.services.redis import RedisService


class AuthResetPasswordInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService,
        data: ResetPasswordRequest,
    ) -> MessageResponse:
        return await auth_service.reset_password(
            session=session,
            redis_service=redis_service,
            data=data,
        )
