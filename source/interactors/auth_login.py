from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import AuthResponse, UserLoginRequest
from source.services.auth import AuthService


class AuthLoginInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        data: UserLoginRequest,
    ) -> AuthResponse:
        return await auth_service.login_user(
            session=session,
            data=data,
        )
