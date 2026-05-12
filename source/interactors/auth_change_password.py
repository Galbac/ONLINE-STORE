from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.user import User
from source.schemas.pydantic.auth import ChangePasswordRequest, MessageResponse
from source.services.auth import AuthService
from source.services.redis import RedisService


class AuthChangePasswordInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService,
        user: User,
        data: ChangePasswordRequest,
        ip_address: str,
        access_token: str | None,
    ) -> MessageResponse:
        return await auth_service.change_password(
            session=session,
            redis_service=redis_service,
            user=user,
            data=data,
            ip_address=ip_address,
            access_token=access_token,
        )
