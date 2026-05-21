from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.notification import NotificationEmailDisabledError, NotificationSendError
from source.errors.settings import EmptyNotificationSettingsUpdateError
from source.schemas.pydantic.notifications import AdminNotificationSettingsResponse, AdminNotificationSettingsUpdateRequest, AdminTestEmailRequest, MessageResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.notifications import EmailService
from source.services.notification_settings_cache import NotificationSettingsCacheService
from source.services.redis import RedisService


class AdminNotificationService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:notifications:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:notifications:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_test_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:notifications:test" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_settings(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        commiter,
        permission_service,
        notification_settings_repository,
        notification_settings_cache_service: NotificationSettingsCacheService,
    ) -> AdminNotificationSettingsResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_settings = await notification_settings_cache_service.get(redis_service=redis_service)
        if cached_settings is not None:
            return cached_settings

        notification_settings, created = await notification_settings_repository.get_or_create_default(session=session)
        if created:
            await commiter.commit()

        response = self._build_response(notification_settings=notification_settings)
        await notification_settings_cache_service.set(
            redis_service=redis_service,
            response=response,
            ttl_seconds=600,
        )
        return response

    async def update_settings(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminNotificationSettingsUpdateRequest,
        commiter,
        permission_service,
        notification_settings_repository,
        notification_settings_cache_service: NotificationSettingsCacheService,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminNotificationSettingsResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyNotificationSettingsUpdateError

        notification_settings, _created = await notification_settings_repository.get_or_create_default(session=session)
        before = {
            field: getattr(notification_settings, field)
            for field in update_fields
        }

        notification_settings = await notification_settings_repository.update(
            session=session,
            notification_settings=notification_settings,
            data=update_fields,
        )

        changes = {}
        for field in update_fields:
            current_value = getattr(notification_settings, field)
            if before[field] != current_value:
                changes[field] = {
                    "old": str(before[field]) if before[field] is not None else None,
                    "new": str(current_value) if current_value is not None else None,
                }

        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_notification_settings_update",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "changes": changes,
            },
        )
        await commiter.commit()
        await notification_settings_cache_service.invalidate(redis_service=redis_service)

        return self._build_response(notification_settings=notification_settings)

    async def send_test_email(
        self,
        *,
        session,
        user,
        data: AdminTestEmailRequest,
        commiter,
        permission_service,
        email_service: EmailService,
        notification_settings_repository,
        notification_log_repository,
    ) -> MessageResponse:
        self._check_test_permission(user=user, permission_service=permission_service)

        subject = data.subject or "Тестовое письмо"
        message = data.message or "Это тестовое email-уведомление из админ-панели интернет-магазина."
        notification_settings, _created = await notification_settings_repository.get_or_create_default(session=session)
        if not settings.email_notifications.enabled or not notification_settings.email_enabled:
            await self._log_test_email(
                session=session,
                notification_log_repository=notification_log_repository,
                user=user,
                email=str(data.email),
                subject=subject,
                message=message,
                status="error",
                error_message="Email-уведомления отключены",
            )
            await commiter.commit()
            raise NotificationEmailDisabledError

        try:
            await email_service.send_email(email=str(data.email), subject=subject, message=message)
        except NotificationEmailDisabledError:
            await self._log_test_email(
                session=session,
                notification_log_repository=notification_log_repository,
                user=user,
                email=str(data.email),
                subject=subject,
                message=message,
                status="error",
                error_message="Email-уведомления отключены",
            )
            await commiter.commit()
            raise
        except Exception as error:
            await self._log_test_email(
                session=session,
                notification_log_repository=notification_log_repository,
                user=user,
                email=str(data.email),
                subject=subject,
                message=message,
                status="error",
                error_message=str(error),
            )
            await commiter.commit()
            raise NotificationSendError from error

        await self._log_test_email(
            session=session,
            notification_log_repository=notification_log_repository,
            user=user,
            email=str(data.email),
            subject=subject,
            message=message,
            status="success",
            error_message=None,
        )
        await commiter.commit()
        return MessageResponse(message="Тестовое email-уведомление отправлено", email=data.email)

    async def _log_test_email(
        self,
        *,
        session,
        notification_log_repository,
        user,
        email: str,
        subject: str,
        message: str,
        status: str,
        error_message: str | None,
    ) -> None:
        await notification_log_repository.create(
            session=session,
            channel="email",
            recipient=email,
            subject=subject,
            message=message,
            status=status,
            error_message=error_message,
            created_by=user.id,
        )

    def _build_response(self, *, notification_settings) -> AdminNotificationSettingsResponse:
        email_from = notification_settings.email_from or settings.email_notifications.from_email or None
        telegram_admin_chat_id = notification_settings.telegram_admin_chat_id or settings.telegram.admin_chat_id or None
        return AdminNotificationSettingsResponse(
            email_enabled=notification_settings.email_enabled and settings.email_notifications.enabled,
            email_from=email_from,
            email_sender_name=notification_settings.email_sender_name,
            telegram_enabled=notification_settings.telegram_enabled and settings.telegram.enabled,
            telegram_admin_chat_id=telegram_admin_chat_id,
            notify_admin_new_order=notification_settings.notify_admin_new_order,
            notify_admin_payment_error=notification_settings.notify_admin_payment_error,
            notify_admin_1c_error=notification_settings.notify_admin_1c_error,
            notify_customer_order_created=notification_settings.notify_customer_order_created,
            notify_customer_order_status=notification_settings.notify_customer_order_status,
            notify_customer_payment=notification_settings.notify_customer_payment,
            notify_customer_delivery=notification_settings.notify_customer_delivery,
            updated_at=notification_settings.updated_date,
        )
