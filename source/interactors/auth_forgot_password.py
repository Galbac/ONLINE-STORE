from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import ForgotPasswordRequest, MessageResponse
from source.services.auth import AuthService
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.redis import RedisService


class AuthForgotPasswordInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        data: ForgotPasswordRequest,
        ip_address: str,
        user_agent: str | None,
    ) -> MessageResponse:
        return await auth_service.forgot_password(
            session=session,
            redis_service=redis_service,
            email_service=email_service,
            telegram_service=telegram_service,
            data=data,
            ip_address=ip_address,
            user_agent=user_agent,
        )
