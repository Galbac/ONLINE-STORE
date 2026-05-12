import asyncio
import smtplib
from email.message import EmailMessage

from source.config.logging import logger
from source.config.settings import settings


class EmailService:
    async def send_password_reset_email(
        self,
        *,
        email: str,
        reset_link: str,
    ) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return

        message = EmailMessage()
        message["Subject"] = "Восстановление пароля"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(
            "Для установки нового пароля перейдите по ссылке:\n"
            f"{reset_link}\n\n"
            "Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.",
        )

        await asyncio.to_thread(self._send_message, message)

    def _send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp.host, settings.smtp.port) as smtp:
            smtp.starttls()
            if settings.smtp.user:
                smtp.login(settings.smtp.user, settings.smtp.password)
            smtp.send_message(message)

#TODO доделать отправку сообщения по телеграм
class TelegramNotificationService:
    async def notify_admin_password_reset_issue(
        self,
        *,
        user_id: int,
        login: str,
    ) -> None:
        logger.info(
            "Password reset requested for user without email: user_id=%s login=%s",
            user_id,
            login,
        )
