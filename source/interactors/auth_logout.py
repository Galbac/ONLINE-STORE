from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.user import User
from source.services.auth import AuthService


class AuthLogoutInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        user: User,
        refresh_token: str,
    ) -> None:
        await auth_service.logout_user(
            session=session,
            user=user,
            refresh_token=refresh_token,
        )
