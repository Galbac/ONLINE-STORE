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

    async def send_order_created_email(self, *, email: str, order_number: str) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return
        message = EmailMessage()
        message["Subject"] = f"Заказ {order_number} создан"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(f"Ваш заказ {order_number} создан.")
        await asyncio.to_thread(self._send_message, message)

    async def send_order_cancelled_email(self, *, email: str, order_number: str) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return
        message = EmailMessage()
        message["Subject"] = f"Заказ {order_number} отменён"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(f"Ваш заказ {order_number} отменён.")
        await asyncio.to_thread(self._send_message, message)

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

    async def notify_admin_order_created(self, *, order_number: str, user_id: int) -> None:
        logger.info("Order created: order_number=%s user_id=%s", order_number, user_id)

    async def notify_admin_order_cancelled(self, *, order_number: str, user_id: int) -> None:
        logger.info("Order cancelled: order_number=%s user_id=%s", order_number, user_id)


class NotificationService:
    async def notify_order_created(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
    ) -> None:
        if order.customer_email:
            await email_service.send_order_created_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_order_created(order_number=order.order_number, user_id=order.user_id)

    async def notify_order_cancelled(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
    ) -> None:
        if order.customer_email:
            await email_service.send_order_cancelled_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_order_cancelled(order_number=order.order_number, user_id=order.user_id)
