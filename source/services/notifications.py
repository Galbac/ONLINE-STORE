import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from source.config.logging import logger
from source.config.settings import settings
from source.errors.auth import InactiveUserError
from source.errors.notification import (
    NotificationAccessDeniedError,
    NotificationEmailDisabledError,
    NotificationNotFoundError,
    NotificationSendError,
    NotificationTelegramChatIdMissingError,
    NotificationTelegramDisabledError,
)
from source.schemas.pydantic.notifications import (
    MessageResponse,
    NotificationListResponse,
    NotificationQueryParams,
    NotificationResponse,
    TestEmailRequest,
    TestTelegramRequest,
)
from source.utils.query_hash import build_query_hash


class EmailService:
    async def send_email(self, *, email: str, subject: str, message: str) -> None:
        if not settings.email_notifications.enabled:
            raise NotificationEmailDisabledError
        if not settings.email_notifications.host or not settings.email_notifications.from_email:
            raise NotificationSendError("Email settings are incomplete")

        email_message = EmailMessage()
        email_message["Subject"] = subject
        email_message["From"] = settings.email_notifications.from_email
        email_message["To"] = email
        email_message.set_content(message)
        await asyncio.to_thread(self._send_email_notification, email_message)

    def _send_email_notification(self, message: EmailMessage) -> None:
        with smtplib.SMTP(settings.email_notifications.host, settings.email_notifications.port) as smtp:
            smtp.starttls()
            if settings.email_notifications.username:
                smtp.login(settings.email_notifications.username, settings.email_notifications.password)
            smtp.send_message(message)

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

    async def send_order_status_changed_email(self, *, email: str, order_number: str, status: str) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return
        message = EmailMessage()
        message["Subject"] = f"Статус заказа {order_number} изменён"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(f"Статус заказа {order_number}: {status}.")
        await asyncio.to_thread(self._send_message, message)

    async def send_payment_success_email(self, *, email: str, order_number: str) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return
        message = EmailMessage()
        message["Subject"] = f"Заказ {order_number} оплачен"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(f"Оплата заказа {order_number} успешно получена.")
        await asyncio.to_thread(self._send_message, message)

    async def send_refund_created_email(self, *, email: str, order_number: str) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return
        message = EmailMessage()
        message["Subject"] = f"По заказу {order_number} создан возврат"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(f"По заказу {order_number} создан возврат.")
        await asyncio.to_thread(self._send_message, message)

#TODO доделать отправку сообщения по телеграм
class TelegramNotificationService:
    async def send_message(self, *, chat_id: str, message: str) -> None:
        if not settings.telegram.enabled:
            raise NotificationTelegramDisabledError
        if not settings.telegram.bot_token:
            raise NotificationSendError("Telegram bot token is not configured")

        await asyncio.to_thread(self._send_telegram_message, chat_id, message)

    def _send_telegram_message(self, chat_id: str, message: str) -> None:
        payload = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{settings.telegram.bot_token}/sendMessage",
            data=payload,
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise NotificationSendError("Telegram send failed")

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

    async def notify_order_status_changed(self, *, order_number: str, user_id: int, status: str) -> None:
        logger.info("Order status changed: order_number=%s user_id=%s status=%s", order_number, user_id, status)

    async def notify_admin_payment_success(self, *, order_number: str, user_id: int) -> None:
        logger.info("Payment succeeded: order_number=%s user_id=%s", order_number, user_id)

    async def notify_admin_refund_created(self, *, order_number: str, user_id: int) -> None:
        logger.info("Refund created: order_number=%s user_id=%s", order_number, user_id)


class NotificationService:
    async def get_user_notifications(
        self,
        *,
        session,
        redis_service,
        user,
        query: NotificationQueryParams,
        notification_repository,
        notification_cache_service,
    ) -> NotificationListResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        query_hash = build_query_hash(query.model_dump())
        cached_notifications = await notification_cache_service.get(
            redis_service=redis_service,
            user_id=user.id,
            query_hash=query_hash,
        )
        if cached_notifications is not None:
            return cached_notifications

        items = await notification_repository.get_by_user_id(
            session=session,
            user_id=user.id,
            query=query,
        )
        total = await notification_repository.count_by_user_id(
            session=session,
            user_id=user.id,
            query=query,
        )
        unread_count = await notification_repository.count_unread_by_user_id(
            session=session,
            user_id=user.id,
        )
        pages = (total + query.limit - 1) // query.limit if total else 0
        response = NotificationListResponse(
            items=items,
            total=total,
            unread_count=unread_count,
            page=query.page,
            limit=query.limit,
            pages=pages,
        )
        await notification_cache_service.set(
            redis_service=redis_service,
            user_id=user.id,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.notifications.cache_ttl_seconds,
        )
        return response

    async def mark_as_read(
        self,
        *,
        session,
        redis_service,
        user,
        notification_id: int,
        notification_repository,
        notification_cache_service,
    ) -> NotificationResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        notification = await notification_repository.get_by_id(session=session, notification_id=notification_id)
        if notification is None:
            raise NotificationNotFoundError
        if notification.user_id != user.id:
            raise NotificationAccessDeniedError

        notification = await notification_repository.mark_as_read(session=session, notification=notification)
        await notification_cache_service.invalidate_user(redis_service=redis_service, user_id=user.id)
        return NotificationResponse(
            id=notification.id,
            type=notification.type,
            title=notification.title,
            message=notification.message,
            is_read=notification.is_read,
            read_at=notification.read_at,
            created_at=notification.created_date,
        )

    async def send_test_email(
        self,
        *,
        session,
        user,
        data: TestEmailRequest,
        email_service: EmailService,
        notification_log_repository,
    ) -> MessageResponse:
        subject = data.subject or "Тестовое письмо"
        message = data.message or "Проверка отправки email"
        try:
            await email_service.send_email(email=str(data.email), subject=subject, message=message)
        except Exception as error:
            await notification_log_repository.create(
                session=session,
                channel="email",
                recipient=str(data.email),
                subject=subject,
                message=message,
                status="failed",
                error_message=str(error),
                created_by=user.id,
            )
            raise

        await notification_log_repository.create(
            session=session,
            channel="email",
            recipient=str(data.email),
            subject=subject,
            message=message,
            status="sent",
            error_message=None,
            created_by=user.id,
        )
        return MessageResponse(message="Тестовое email-уведомление отправлено", email=data.email)

    async def send_test_telegram(
        self,
        *,
        session,
        user,
        data: TestTelegramRequest,
        telegram_service: TelegramNotificationService,
        notification_log_repository,
    ) -> MessageResponse:
        chat_id = data.chat_id or settings.telegram.admin_chat_id
        if not chat_id:
            raise NotificationTelegramChatIdMissingError

        message = data.message or "Тестовое уведомление из интернет-магазина"
        try:
            await telegram_service.send_message(chat_id=chat_id, message=message)
        except Exception as error:
            await notification_log_repository.create(
                session=session,
                channel="telegram",
                recipient=chat_id,
                subject=None,
                message=message,
                status="failed",
                error_message=str(error),
                created_by=user.id,
            )
            raise

        await notification_log_repository.create(
            session=session,
            channel="telegram",
            recipient=chat_id,
            subject=None,
            message=message,
            status="sent",
            error_message=None,
            created_by=user.id,
        )
        return MessageResponse(message="Тестовое Telegram-уведомление отправлено", chat_id=chat_id)

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

    async def notify_order_status_changed(
        self,
        *,
        session,
        order,
        notification_repository,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
    ) -> None:
        title = f"Статус заказа {order.order_number} изменён"
        message = f"Новый статус заказа {order.order_number}: {order.status}"
        await notification_repository.create(
            session=session,
            user_id=order.user_id,
            type="order_status",
            title=title,
            message=message,
        )
        if order.customer_email:
            await email_service.send_order_status_changed_email(
                email=order.customer_email,
                order_number=order.order_number,
                status=order.status,
            )
        await telegram_service.notify_order_status_changed(
            order_number=order.order_number,
            user_id=order.user_id,
            status=order.status,
        )

    async def notify_payment_success(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
    ) -> None:
        if order.customer_email:
            await email_service.send_payment_success_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_payment_success(order_number=order.order_number, user_id=order.user_id)

    async def notify_refund_created(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
    ) -> None:
        if order.customer_email:
            await email_service.send_refund_created_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_refund_created(order_number=order.order_number, user_id=order.user_id)
