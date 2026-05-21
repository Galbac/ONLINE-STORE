from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.delivery import AdminDeliverySettingsResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.admin_delivery_cache import AdminDeliveryCacheService
from source.services.redis import RedisService


class AdminDeliveryService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:delivery:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_settings(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_settings_repository,
    ) -> AdminDeliverySettingsResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_settings = await admin_delivery_cache_service.get_settings(redis_service=redis_service)
        if cached_settings is not None:
            return cached_settings

        delivery_settings, created = await delivery_settings_repository.get_or_create_default(session=session)
        if created:
            await commiter.commit()

        response = self._build_response(delivery_settings=delivery_settings)
        await admin_delivery_cache_service.set_settings(
            redis_service=redis_service,
            response=response,
            ttl_seconds=settings.admin_delivery.settings_cache_ttl_seconds,
        )
        return response

    def _build_response(self, *, delivery_settings) -> AdminDeliverySettingsResponse:
        return AdminDeliverySettingsResponse(
            delivery_enabled=delivery_settings.delivery_enabled,
            pickup_enabled=delivery_settings.pickup_enabled,
            min_order_amount=delivery_settings.min_order_amount,
            base_delivery_price=delivery_settings.base_price,
            free_delivery_from=delivery_settings.free_from_amount,
            time_slots_enabled=delivery_settings.has_time_slots,
            delivery_comment=delivery_settings.delivery_description,
            pickup_comment=delivery_settings.pickup_description,
            default_city=getattr(delivery_settings, "default_city", "Москва"),
            currency=getattr(delivery_settings, "currency", settings.payments.currency),
            updated_at=getattr(delivery_settings, "updated_date", None),
        )
