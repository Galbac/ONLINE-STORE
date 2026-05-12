from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import AuthResponse, UserRegisterRequest
from source.services.auth import AuthService


class AuthRegisterInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        data: UserRegisterRequest,
    ) -> AuthResponse:
        return await auth_service.register_user(
            session=session,
            data=data,
        )
