from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import RefreshTokenRequest, TokenPairResponse
from source.services.auth import AuthService
from source.services.redis import RedisService


class AuthRefreshInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService,
        data: RefreshTokenRequest,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenPairResponse:
        return await auth_service.refresh_tokens(
            session=session,
            redis_service=redis_service,
            data=data,
            ip_address=ip_address,
            user_agent=user_agent,
        )
