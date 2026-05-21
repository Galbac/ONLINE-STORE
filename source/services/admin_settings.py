from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.settings import AdminSettingsResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService


class AdminSettingsService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:settings:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_settings(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        commiter,
        permission_service,
        settings_repository,
        delivery_settings_repository,
        settings_cache_service,
    ) -> AdminSettingsResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_settings = await settings_cache_service.get_admin_settings(redis_service=redis_service)
        if cached_settings is not None:
            return cached_settings

        store_settings, store_created = await settings_repository.get_or_create_default(session=session)
        delivery_settings, delivery_created = await delivery_settings_repository.get_or_create_default(session=session)
        if store_created or delivery_created:
            await commiter.commit()

        response = self._build_response(
            store_settings=store_settings,
            delivery_settings=delivery_settings,
        )
        await settings_cache_service.set_admin_settings(
            redis_service=redis_service,
            response=response,
            ttl_seconds=settings.admin_settings.cache_ttl_seconds,
        )
        return response

    def _build_response(self, *, store_settings, delivery_settings) -> AdminSettingsResponse:
        updated_at_values = [
            value
            for value in (
                getattr(store_settings, "updated_date", None),
                getattr(delivery_settings, "updated_date", None),
            )
            if value is not None
        ]
        return AdminSettingsResponse(
            shop_name=store_settings.shop_name,
            phone=store_settings.phone,
            email=store_settings.email,
            address=store_settings.address,
            working_hours=store_settings.working_hours,
            default_city=delivery_settings.default_city,
            currency=delivery_settings.currency,
            delivery_enabled=delivery_settings.delivery_enabled,
            pickup_enabled=delivery_settings.pickup_enabled,
            online_payment_enabled=store_settings.online_payment_enabled,
            pay_on_delivery_enabled=store_settings.pay_on_delivery_enabled,
            min_order_amount=delivery_settings.min_order_amount,
            maintenance_mode=store_settings.maintenance_mode,
            updated_at=max(updated_at_values) if updated_at_values else None,
        )
