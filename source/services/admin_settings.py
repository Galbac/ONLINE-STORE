from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.settings import EmptyAdminSettingsUpdateError
from source.schemas.pydantic.settings import AdminSettingsResponse, AdminSettingsUpdateRequest
from source.services.admin_auth import STAFF_ROLES
from source.services.delivery_cache import DeliveryCacheService
from source.services.redis import RedisService


class AdminSettingsService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:settings:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:settings:update" not in permission_service.get_user_permissions(role=user.role):
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

    async def update_settings(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminSettingsUpdateRequest,
        commiter,
        permission_service,
        settings_repository,
        delivery_settings_repository,
        settings_cache_service,
        delivery_cache_service: DeliveryCacheService,
        cart_cache_service,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminSettingsResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyAdminSettingsUpdateError

        store_settings, _store_created = await settings_repository.get_or_create_default(session=session)
        delivery_settings, _delivery_created = await delivery_settings_repository.get_or_create_default(session=session)

        store_fields = {
            "shop_name",
            "phone",
            "email",
            "address",
            "working_hours",
            "online_payment_enabled",
            "pay_on_delivery_enabled",
            "maintenance_mode",
        }
        delivery_fields = {
            "default_city",
            "currency",
            "delivery_enabled",
            "pickup_enabled",
            "min_order_amount",
        }
        store_update = {field: value for field, value in update_fields.items() if field in store_fields}
        delivery_update = {field: value for field, value in update_fields.items() if field in delivery_fields}

        before = {
            field: getattr(store_settings, field)
            for field in store_update
        } | {
            field: getattr(delivery_settings, field)
            for field in delivery_update
        }

        if store_update:
            store_settings = await settings_repository.update(
                session=session,
                store_settings=store_settings,
                data=store_update,
            )
        if delivery_update:
            delivery_settings = await delivery_settings_repository.update(
                session=session,
                delivery_settings=delivery_settings,
                data=delivery_update,
            )

        changes = {}
        for field in update_fields:
            source = store_settings if field in store_fields else delivery_settings
            current_value = getattr(source, field)
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
            event="admin_settings_update",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await settings_cache_service.invalidate_admin_settings(redis_service=redis_service)
        await settings_cache_service.invalidate_public_settings(redis_service=redis_service)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)
        await cart_cache_service.invalidate_all_summaries(redis_service=redis_service)

        return self._build_response(
            store_settings=store_settings,
            delivery_settings=delivery_settings,
        )

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
