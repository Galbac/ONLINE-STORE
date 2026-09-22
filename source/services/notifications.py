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
        with smtplib.SMTP(settings.email_notifications.host, settings.email_notifications.port, timeout=10) as smtp:
            if settings.email_notifications.use_tls:
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

    async def send_register_otp_email(
        self,
        *,
        email: str,
        code: str,
    ) -> None:
        from_email = settings.smtp.from_email or settings.email_notifications.from_email or "no-reply@grocerystore.local"
        host = settings.smtp.host or settings.email_notifications.host

        message = EmailMessage()
        message["Subject"] = f"{code} — ваш код подтверждения в Grocery Store"
        message["From"] = from_email
        message["To"] = email

        plain_text = (
            f"Здравствуйте!\n\n"
            f"Ваш проверочный код для регистрации в Grocery Store: {code}\n\n"
            f"Код действителен в течение 10 минут. Никому не сообщайте его.\n\n"
            f"С уважением,\nКоманда Grocery Store"
        )
        message.set_content(plain_text)

        html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Код подтверждения регистрации</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 36px 16px;">
    <tr>
      <td align="center">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 500px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
          <tr>
            <td style="background: linear-gradient(135deg, #059669 0%, #0d9488 100%); padding: 32px 30px; text-align: center;">
              <div style="display: inline-block; background-color: rgba(255, 255, 255, 0.2); border-radius: 14px; padding: 10px 14px; margin-bottom: 10px; font-size: 28px; line-height: 1;">
                🛒
              </div>
              <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 800; letter-spacing: -0.3px;">Grocery Store</h1>
              <p style="margin: 4px 0 0; color: #d1fae5; font-size: 13px; font-weight: 500;">Свежие продукты к вашему столу</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 32px 32px 28px;">
              <h2 style="margin: 0 0 10px; color: #0f172a; font-size: 19px; font-weight: 700; text-align: center;">Подтверждение регистрации</h2>
              <p style="margin: 0 0 22px; color: #475569; font-size: 14px; line-height: 1.6; text-align: center;">
                Вы указали этот адрес для создания аккаунта. Введите 4-значный код для подтверждения:
              </p>
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 24px 0;">
                <tr>
                  <td align="center">
                    <div style="background-color: #f0fdf4; border: 2px dashed #059669; border-radius: 16px; padding: 18px 30px; display: inline-block; text-align: center;">
                      <span style="font-family: 'Courier New', Courier, monospace, monospace; font-size: 40px; font-weight: 800; letter-spacing: 12px; color: #065f46; display: inline-block; padding-left: 12px;">
                        {code}
                      </span>
                    </div>
                  </td>
                </tr>
              </table>
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-radius: 12px; padding: 14px 18px; margin-bottom: 22px; border: 1px solid #f1f5f9;">
                <tr>
                  <td>
                    <p style="margin: 0 0 4px; font-size: 12.5px; color: #334155;">
                      ⏱ <strong>Срок действия:</strong> код активен <strong>10 минут</strong>.
                    </p>
                    <p style="margin: 0; font-size: 12.5px; color: #334155;">
                      🔒 <strong>Безопасность:</strong> никогда и никому не передавайте этот код.
                    </p>
                  </td>
                </tr>
              </table>
              <p style="margin: 0; color: #94a3b8; font-size: 11.5px; line-height: 1.5; text-align: center;">
                Если вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 30px; text-align: center;">
              <p style="margin: 0 0 3px; font-size: 12px; font-weight: 600; color: #64748b;">
                Команда Grocery Store
              </p>
              <p style="margin: 0; font-size: 11px; color: #94a3b8;">
                © 2026 Grocery Store. Все права защищены.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
        message.add_alternative(html_content, subtype="html")

        if not host:
            logger.info("✉️ [DEV OTP] Регистрация для %s: код %s", email, code)
            return

        try:
            await asyncio.to_thread(self._send_message, message)
            logger.info("✉️ [SMTP] Код подтверждения отправлен на %s", email)
        except Exception as err:
            logger.warning("✉️ [SMTP Error] Не удалось отправить письмо через SMTP (%s). DEV OTP для %s: %s", err, email, code)

    def _send_message(self, message: EmailMessage) -> None:
        host = settings.smtp.host or settings.email_notifications.host
        port = settings.smtp.port or settings.email_notifications.port
        user = settings.smtp.user or settings.email_notifications.username
        password = settings.smtp.password or settings.email_notifications.password
        use_tls = settings.email_notifications.use_tls

        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
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

    async def send_order_confirmed_email(self, *, email: str, order_number: str) -> None:
        if not settings.smtp.host or not settings.smtp.from_email:
            return
        message = EmailMessage()
        message["Subject"] = f"Заказ {order_number} подтверждён"
        message["From"] = settings.smtp.from_email
        message["To"] = email
        message.set_content(f"Ваш заказ {order_number} подтверждён.")
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

    async def notify_order_confirmed(self, *, order_number: str, user_id: int) -> None:
        logger.info("Order confirmed: order_number=%s user_id=%s", order_number, user_id)

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
        session=None,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if order.customer_email:
            await email_service.send_order_created_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_order_created(order_number=order.order_number, user_id=order.user_id)
        if web_push_service is not None and push_subscription_repository is not None and session is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title=f"Заказ {order.order_number} оформлен! 🎉",
                body="Мы начали сборку продуктов. Скоро курьер отправится к вам.",
                url=target_url,
            )

    async def notify_order_cancelled(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
        session=None,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if order.customer_email:
            await email_service.send_order_cancelled_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_order_cancelled(order_number=order.order_number, user_id=order.user_id)
        if web_push_service is not None and push_subscription_repository is not None and session is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title=f"Заказ {order.order_number} отменен",
                body="Заказ отменен. Если средства были списаны, они вернутся в ближайшее время.",
                url=target_url,
            )

    async def notify_order_status_changed(
        self,
        *,
        session,
        order,
        notification_repository,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        web_push_service=None,
        push_subscription_repository=None,
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
        if web_push_service is not None and push_subscription_repository is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"

            status_str = str(getattr(order, "status", "")).lower()
            if "deliver" in status_str and "ing" in status_str:
                push_title = f"Курьер уже в пути к вам! 🚴"
                push_body = f"Курьер везет заказ {order.order_number}. Примерное время прибытия: 20-30 мин."
            elif "deliv" in status_str and "ed" in status_str:
                push_title = f"Заказ {order.order_number} доставлен! 🍏"
                push_body = "Приятного аппетита! Будем рады вашей оценке заказа в приложении."
            elif "pickup" in status_str or "ready" in status_str:
                push_title = f"Заказ {order.order_number} готов к выдаче! 📦"
                push_body = "Ваш заказ собран и ожидает вас в пункте самовывоза."
            elif "assembly" in status_str:
                push_title = f"Сборка заказа {order.order_number} 🛍"
                push_body = "Собираем самые свежие продукты для вашего заказа."
            else:
                push_title = title
                push_body = message

            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title=push_title,
                body=push_body,
                url=target_url,
            )

    async def notify_order_confirmed(
        self,
        *,
        session,
        order,
        notification_repository,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        title = f"Заказ {order.order_number} подтверждён"
        message = f"Ваш заказ {order.order_number} подтверждён."
        await notification_repository.create(
            session=session,
            user_id=order.user_id,
            type="order_status",
            title=title,
            message=message,
        )
        if order.customer_email:
            await email_service.send_order_confirmed_email(
                email=order.customer_email,
                order_number=order.order_number,
            )
        await telegram_service.notify_order_confirmed(order_number=order.order_number, user_id=order.user_id)
        if web_push_service is not None and push_subscription_repository is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title=title,
                body=message,
                url=target_url,
            )

    async def notify_payment_success(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
        session=None,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if order.customer_email:
            await email_service.send_payment_success_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_payment_success(order_number=order.order_number, user_id=order.user_id)
        if web_push_service is not None and push_subscription_repository is not None and session is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"
            amount_str = f" на сумму {order.total_amount} ₽" if getattr(order, "total_amount", None) else ""
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title="Оплата получена ✅",
                body=f"Оплата{amount_str} по заказу {order.order_number} успешно завершена. Чек сформирован.",
                url=target_url,
            )

    async def notify_refund_created(
        self,
        *,
        email_service: EmailService,
        telegram_service: TelegramNotificationService,
        order,
        session=None,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if order.customer_email:
            await email_service.send_refund_created_email(email=order.customer_email, order_number=order.order_number)
        await telegram_service.notify_admin_refund_created(order_number=order.order_number, user_id=order.user_id)
        if web_push_service is not None and push_subscription_repository is not None and session is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title="Оформлен возврат средств",
                body=f"По заказу {order.order_number} оформлен возврат. Средства поступят в соответствии со сроками вашего банка.",
                url=target_url,
            )

    async def notify_stock_replenished(
        self,
        *,
        session,
        product,
        stock_alerts,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> int:
        notified = 0
        for alert in stock_alerts:
            if getattr(alert, "is_notified", False):
                continue
            if web_push_service is not None and push_subscription_repository is not None and getattr(alert, "user_id", None):
                target_url = f"/product/{product.slug}" if getattr(product, "slug", None) else "/catalog"
                await web_push_service.send_to_user(
                    session=session,
                    push_subscription_repository=push_subscription_repository,
                    user_id=alert.user_id,
                    title="Товар снова в наличии! 🥑",
                    body=f"«{product.name}» снова доступен для заказа.",
                    url=target_url,
                )
            alert.is_notified = True
            notified += 1
        return notified

    async def notify_loyalty_points_credited(
        self,
        *,
        session,
        user_id: int,
        points: int,
        reason: str = "за покупку",
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if web_push_service is not None and push_subscription_repository is not None and user_id:
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=user_id,
                title="Начислены бонусы лояльности! 🎁",
                body=f"Вам начислено +{points} бонусов {reason}. Используйте их при следующем заказе!",
                url="/profile/loyalty",
            )

    async def notify_payment_failed(
        self,
        *,
        session,
        order,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if web_push_service is not None and push_subscription_repository is not None and getattr(order, "user_id", None):
            order_id = getattr(order, "id", None)
            target_url = f"/profile/orders/{order_id}" if order_id else "/profile/orders"
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=order.user_id,
                title="Не удалось провести оплату ⚠️",
                body=f"Оплата по заказу {order.order_number} не прошла. Пожалуйста, выберите другой способ оплаты в приложении.",
                url=target_url,
            )

    async def notify_abandoned_cart(
        self,
        *,
        session,
        user_id: int,
        items_count: int = 1,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> None:
        if web_push_service is not None and push_subscription_repository is not None and user_id:
            await web_push_service.send_to_user(
                session=session,
                push_subscription_repository=push_subscription_repository,
                user_id=user_id,
                title="Вы кое-что забыли в корзине 🛒",
                body=f"Ваши свежие товары ({items_count} поз.) ждут вас. Завершите заказ, пока продукты есть в наличии!",
                url="/cart",
            )
