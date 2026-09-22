from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.auth import SendRegisterOtpRequest, SendRegisterOtpResponse
from source.services.auth import AuthService
from source.services.notifications import EmailService
from source.services.redis import RedisService


class AuthSendRegisterOtpInteractor:
    async def execute(
        self,
        *,
        session: AsyncSession,
        auth_service: AuthService,
        redis_service: RedisService,
        email_service: EmailService,
        data: SendRegisterOtpRequest,
        ip_address: str,
    ) -> SendRegisterOtpResponse:
        return await auth_service.send_register_otp(
            session=session,
            redis_service=redis_service,
            email_service=email_service,
            data=data,
            ip_address=ip_address,
        )
