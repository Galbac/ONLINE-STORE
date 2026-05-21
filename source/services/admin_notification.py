from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.notifications import AdminNotificationSettingsResponse
from source.services.admin_auth import STAFF_ROLES
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
