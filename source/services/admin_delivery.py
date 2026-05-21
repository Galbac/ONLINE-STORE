from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.delivery import (
    DeliveryZoneActiveOrdersError,
    DeliveryZoneAlreadyExistsError,
    DeliveryZoneNotFoundError,
    EmptyDeliverySettingsUpdateError,
    EmptyDeliveryZoneUpdateError,
    PickupPointAlreadyExistsError,
    PickupPointAdminNotFoundError,
    PickupPointActiveOrdersError,
    EmptyPickupPointUpdateError,
)
from source.schemas.pydantic.delivery import (
    AdminDeliverySettingsResponse,
    AdminDeliverySettingsUpdateRequest,
    AdminDeliveryZoneCreateRequest,
    AdminDeliveryZoneListQueryParams,
    AdminDeliveryZoneListResponse,
    AdminDeliveryZoneResponse,
    AdminDeliveryZoneUpdateRequest,
    AdminPickupPointCreateRequest,
    AdminPickupPointListQueryParams,
    AdminPickupPointListResponse,
    AdminPickupPointResponse,
    AdminPickupPointUpdateRequest,
    MessageResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.admin_delivery_cache import AdminDeliveryCacheService
from source.services.delivery_cache import DeliveryCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminDeliveryService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:delivery:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:delivery:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:delivery:create" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_delete_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:delivery:delete" not in permission_service.get_user_permissions(role=user.role):
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

    async def get_zones(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminDeliveryZoneListQueryParams,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_zone_repository,
    ) -> AdminDeliveryZoneListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        permissions = permission_service.get_user_permissions(role=user.role)
        if query.include_deleted and "admin:delivery:read_deleted" not in permissions:
            raise AdminAuthAccessDeniedError

        normalized_query = query.model_copy(
            update={
                "q": normalize_search_query(query.q) if query.q is not None else None,
                "city": query.city.strip() if query.city is not None else None,
            },
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_zones = await admin_delivery_cache_service.get_zones(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_zones is not None:
            return cached_zones

        zones = await delivery_zone_repository.get_list(session=session, query=normalized_query)
        items = [self._build_zone_response(zone=zone) for zone in zones]
        total = await delivery_zone_repository.count(session=session, query=normalized_query)
        response = AdminDeliveryZoneListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_delivery_cache_service.set_zones(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.admin_delivery.zones_cache_ttl_seconds,
        )
        return response

    async def get_pickup_points(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminPickupPointListQueryParams,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        pickup_point_repository,
    ) -> AdminPickupPointListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={
                "q": normalize_search_query(query.q) if query.q is not None else None,
                "city": query.city.strip() if query.city is not None else None,
            },
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_pickup_points = await admin_delivery_cache_service.get_pickup_points(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_pickup_points is not None:
            return cached_pickup_points

        pickup_points = await pickup_point_repository.get_list(session=session, query=normalized_query)
        total = await pickup_point_repository.count(session=session, query=normalized_query)
        response = AdminPickupPointListResponse.build(
            items=[self._build_pickup_point_response(pickup_point=pickup_point) for pickup_point in pickup_points],
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_delivery_cache_service.set_pickup_points(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.admin_delivery.pickup_points_cache_ttl_seconds,
        )
        return response

    async def create_pickup_point(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminPickupPointCreateRequest,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        pickup_point_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminPickupPointResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        existing_pickup_point = await pickup_point_repository.get_by_city_and_address(
            session=session,
            city=data.city,
            address=data.address,
        )
        if existing_pickup_point is not None:
            raise PickupPointAlreadyExistsError

        created_pickup_point = await pickup_point_repository.create(session=session, data=data)
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="create_pickup_point",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "pickup_point_id": created_pickup_point.id,
                "name": created_pickup_point.name,
                "city": created_pickup_point.city,
                "address": created_pickup_point.address,
            },
        )
        await commiter.commit()

        await admin_delivery_cache_service.invalidate_pickup_points(redis_service=redis_service)
        await delivery_cache_service.invalidate_pickup_points(redis_service=redis_service)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)

        return self._build_pickup_point_response(pickup_point=created_pickup_point)

    async def update_pickup_point(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        point_id: int,
        data: AdminPickupPointUpdateRequest,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        pickup_point_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminPickupPointResponse:
        self._check_update_permission(user=user, permission_service=permission_service)
        if point_id <= 0:
            raise ValueError("Неверный point_id")

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyPickupPointUpdateError

        pickup_point = await pickup_point_repository.get_by_id(session=session, pickup_point_id=point_id)
        if pickup_point is None or pickup_point.is_deleted:
            raise PickupPointAdminNotFoundError

        next_city = update_fields.get("city", pickup_point.city)
        next_address = update_fields.get("address", pickup_point.address)
        if next_city != pickup_point.city or next_address != pickup_point.address:
            existing_pickup_point = await pickup_point_repository.get_by_city_and_address(
                session=session,
                city=next_city,
                address=next_address,
            )
            if existing_pickup_point is not None and existing_pickup_point.id != pickup_point.id:
                raise PickupPointAlreadyExistsError

        before = {field: getattr(pickup_point, field) for field in update_fields}
        updated_pickup_point = await pickup_point_repository.update(
            session=session,
            pickup_point=pickup_point,
            data=update_fields,
        )
        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_pickup_point, field)) if getattr(updated_pickup_point, field) is not None else None,
            }
            for field in update_fields
            if before[field] != getattr(updated_pickup_point, field)
        }
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="update_pickup_point",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "pickup_point_id": updated_pickup_point.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await admin_delivery_cache_service.invalidate_pickup_points(redis_service=redis_service)
        await delivery_cache_service.invalidate_pickup_point(redis_service=redis_service, point_id=updated_pickup_point.id)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)

        return self._build_pickup_point_response(pickup_point=updated_pickup_point)

    async def delete_pickup_point(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        point_id: int,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        pickup_point_repository,
        order_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> MessageResponse:
        self._check_delete_permission(user=user, permission_service=permission_service)
        if point_id <= 0:
            raise ValueError("Неверный point_id")

        pickup_point = await pickup_point_repository.get_by_id(session=session, pickup_point_id=point_id)
        if pickup_point is None or pickup_point.is_deleted:
            raise PickupPointAdminNotFoundError

        if await order_repository.exists_active_by_pickup_point_id(session=session, pickup_point_id=pickup_point.id):
            raise PickupPointActiveOrdersError

        deleted_pickup_point = await pickup_point_repository.soft_delete(
            session=session,
            pickup_point=pickup_point,
            deleted_by=user.id,
        )
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="delete_pickup_point",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "pickup_point_id": deleted_pickup_point.id,
                "name": deleted_pickup_point.name,
                "city": deleted_pickup_point.city,
                "address": deleted_pickup_point.address,
            },
        )
        await commiter.commit()

        await admin_delivery_cache_service.invalidate_pickup_points(redis_service=redis_service)
        await delivery_cache_service.invalidate_pickup_point(redis_service=redis_service, point_id=deleted_pickup_point.id)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)

        return MessageResponse(message="Точка самовывоза удалена")

    async def create_zone(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminDeliveryZoneCreateRequest,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        delivery_zone_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminDeliveryZoneResponse:
        self._check_create_permission(user=user, permission_service=permission_service)
        self._validate_zone_create(data=data)

        existing_zone = await delivery_zone_repository.get_by_name_and_city(
            session=session,
            name=data.name,
            city=data.city,
        )
        if existing_zone is not None:
            raise DeliveryZoneAlreadyExistsError

        created_zone = await delivery_zone_repository.create(session=session, data=data)
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="create_delivery_zone",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "zone_id": created_zone.id,
                "name": created_zone.name,
                "city": created_zone.city,
            },
        )
        await commiter.commit()

        await admin_delivery_cache_service.invalidate_zones(redis_service=redis_service)
        await delivery_cache_service.invalidate_calculate(redis_service=redis_service)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)

        return self._build_zone_response(zone=created_zone)

    async def update_zone(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        zone_id: int,
        data: AdminDeliveryZoneUpdateRequest,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        delivery_zone_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminDeliveryZoneResponse:
        self._check_update_permission(user=user, permission_service=permission_service)
        if zone_id <= 0:
            raise ValueError("Неверный zone_id")

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyDeliveryZoneUpdateError

        zone = await delivery_zone_repository.get_by_id(session=session, zone_id=zone_id)
        if zone is None or zone.is_deleted:
            raise DeliveryZoneNotFoundError

        self._validate_zone_update(zone=zone, update_fields=update_fields)

        next_name = update_fields.get("name", zone.name)
        next_city = update_fields.get("city", zone.city)
        if next_name != zone.name or next_city != zone.city:
            existing_zone = await delivery_zone_repository.get_by_name_and_city(
                session=session,
                name=next_name,
                city=next_city,
            )
            if existing_zone is not None and existing_zone.id != zone.id:
                raise DeliveryZoneAlreadyExistsError

        before = {field: getattr(zone, field) for field in update_fields}
        updated_zone = await delivery_zone_repository.update(
            session=session,
            zone=zone,
            data=update_fields,
        )
        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_zone, field)) if getattr(updated_zone, field) is not None else None,
            }
            for field in update_fields
            if before[field] != getattr(updated_zone, field)
        }
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="update_delivery_zone",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "zone_id": updated_zone.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await admin_delivery_cache_service.invalidate_zones(redis_service=redis_service)
        await delivery_cache_service.invalidate_calculate(redis_service=redis_service)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)

        return self._build_zone_response(zone=updated_zone)

    async def delete_zone(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        zone_id: int,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        delivery_zone_repository,
        order_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> MessageResponse:
        self._check_delete_permission(user=user, permission_service=permission_service)
        if zone_id <= 0:
            raise ValueError("Неверный zone_id")

        zone = await delivery_zone_repository.get_by_id(session=session, zone_id=zone_id)
        if zone is None or zone.is_deleted:
            raise DeliveryZoneNotFoundError

        if await order_repository.exists_active_by_delivery_zone_id(session=session, delivery_zone_id=zone.id):
            raise DeliveryZoneActiveOrdersError

        deleted_zone = await delivery_zone_repository.soft_delete(
            session=session,
            zone=zone,
            deleted_by=user.id,
        )
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="delete_delivery_zone",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "actor_id": user.id,
                "zone_id": deleted_zone.id,
                "name": deleted_zone.name,
                "city": deleted_zone.city,
            },
        )
        await commiter.commit()

        await admin_delivery_cache_service.invalidate_zones(redis_service=redis_service)
        await delivery_cache_service.invalidate_calculate(redis_service=redis_service)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)

        return MessageResponse(message="Зона доставки удалена")

    async def update_settings(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminDeliverySettingsUpdateRequest,
        commiter,
        permission_service,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
        delivery_settings_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminDeliverySettingsResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyDeliverySettingsUpdateError

        delivery_settings, created = await delivery_settings_repository.get_or_create_default(session=session)
        repository_data = self._to_repository_data(update_fields=update_fields)
        self._validate_update(delivery_settings=delivery_settings, repository_data=repository_data)

        before = {
            field: getattr(delivery_settings, field)
            for field in repository_data
        }
        updated_settings = await delivery_settings_repository.update(
            session=session,
            delivery_settings=delivery_settings,
            data=repository_data,
        )
        changes = {
            self._response_field(field): {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_settings, field)) if getattr(updated_settings, field) is not None else None,
            }
            for field in repository_data
            if before[field] != getattr(updated_settings, field)
        }
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_delivery_settings_update",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "created_default": created,
                "changes": changes,
            },
        )
        await commiter.commit()

        await self._invalidate_cache(
            redis_service=redis_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
        )
        return self._build_response(delivery_settings=updated_settings)

    def _to_repository_data(self, *, update_fields: dict) -> dict:
        field_map = {
            "base_delivery_price": "base_price",
            "free_delivery_from": "free_from_amount",
            "time_slots_enabled": "has_time_slots",
            "delivery_comment": "delivery_description",
            "pickup_comment": "pickup_description",
        }
        return {
            field_map.get(field, field): value
            for field, value in update_fields.items()
        }

    def _response_field(self, field: str) -> str:
        field_map = {
            "base_price": "base_delivery_price",
            "free_from_amount": "free_delivery_from",
            "has_time_slots": "time_slots_enabled",
            "delivery_description": "delivery_comment",
            "pickup_description": "pickup_comment",
        }
        return field_map.get(field, field)

    def _validate_update(self, *, delivery_settings, repository_data: dict) -> None:
        non_nullable_fields = {"delivery_enabled", "pickup_enabled", "min_order_amount", "base_price", "has_time_slots", "currency"}
        if any(field in repository_data and repository_data[field] is None for field in non_nullable_fields):
            raise ValueError("Неверные настройки доставки")

        if repository_data.get("min_order_amount") is not None and repository_data["min_order_amount"] < 0:
            raise ValueError("Минимальная сумма заказа не может быть отрицательной")
        if repository_data.get("base_price") is not None and repository_data["base_price"] < 0:
            raise ValueError("Стоимость доставки не может быть отрицательной")
        if repository_data.get("free_from_amount") is not None and repository_data["free_from_amount"] < 0:
            raise ValueError("Сумма бесплатной доставки не может быть отрицательной")

        currency = repository_data.get("currency")
        if currency is not None and currency not in settings.admin_delivery.supported_currencies:
            raise ValueError("Неподдерживаемая валюта")

        next_min_order_amount = repository_data.get("min_order_amount", delivery_settings.min_order_amount)
        next_free_from_amount = repository_data.get("free_from_amount", delivery_settings.free_from_amount)
        if next_free_from_amount is not None and next_free_from_amount < next_min_order_amount:
            raise ValueError("Сумма бесплатной доставки не может быть меньше минимальной суммы заказа")

    def _validate_zone_create(self, *, data: AdminDeliveryZoneCreateRequest) -> None:
        if data.delivery_price < 0:
            raise ValueError("Стоимость доставки не может быть отрицательной")
        if data.min_order_amount < 0:
            raise ValueError("Минимальная сумма заказа не может быть отрицательной")
        if data.free_delivery_from is not None and data.free_delivery_from < 0:
            raise ValueError("Сумма бесплатной доставки не может быть отрицательной")
        if data.sort_order < 0:
            raise ValueError("sort_order не может быть отрицательным")
        if data.free_delivery_from is not None and data.free_delivery_from < data.min_order_amount:
            raise ValueError("Сумма бесплатной доставки не может быть меньше минимальной суммы заказа")

    def _validate_zone_update(self, *, zone, update_fields: dict) -> None:
        delivery_price = update_fields.get("delivery_price")
        if delivery_price is not None and delivery_price < 0:
            raise ValueError("Стоимость доставки не может быть отрицательной")
        min_order_amount = update_fields.get("min_order_amount")
        if min_order_amount is not None and min_order_amount < 0:
            raise ValueError("Минимальная сумма заказа не может быть отрицательной")
        free_delivery_from = update_fields.get("free_delivery_from")
        if free_delivery_from is not None and free_delivery_from < 0:
            raise ValueError("Сумма бесплатной доставки не может быть отрицательной")
        sort_order = update_fields.get("sort_order")
        if sort_order is not None and sort_order < 0:
            raise ValueError("sort_order не может быть отрицательным")

        next_min_order_amount = update_fields.get("min_order_amount", zone.min_order_amount)
        next_free_delivery_from = update_fields.get("free_delivery_from", zone.free_delivery_from)
        if next_free_delivery_from is not None and next_min_order_amount is not None and next_free_delivery_from < next_min_order_amount:
            raise ValueError("Сумма бесплатной доставки не может быть меньше минимальной суммы заказа")

    async def _invalidate_cache(
        self,
        *,
        redis_service: RedisService,
        admin_delivery_cache_service: AdminDeliveryCacheService,
        delivery_cache_service: DeliveryCacheService,
    ) -> None:
        await admin_delivery_cache_service.invalidate_settings(redis_service=redis_service)
        await admin_delivery_cache_service.invalidate_zones(redis_service=redis_service)
        await delivery_cache_service.invalidate_options(redis_service=redis_service)
        await delivery_cache_service.invalidate_calculate(redis_service=redis_service)
        await delivery_cache_service.invalidate_time_slots(redis_service=redis_service)
        await redis_service.delete_by_pattern("cart:summary:*")

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

    def _build_zone_response(self, *, zone) -> AdminDeliveryZoneResponse:
        return AdminDeliveryZoneResponse(
            id=zone.id,
            name=zone.name,
            city=zone.city,
            description=zone.description,
            delivery_price=zone.delivery_price,
            free_delivery_from=zone.free_delivery_from,
            min_order_amount=zone.min_order_amount,
            is_active=zone.is_active,
            is_deleted=zone.is_deleted,
            sort_order=zone.sort_order,
            created_at=zone.created_date,
            updated_at=zone.updated_date,
        )

    def _build_pickup_point_response(self, *, pickup_point) -> AdminPickupPointResponse:
        return AdminPickupPointResponse(
            id=pickup_point.id,
            name=pickup_point.name,
            city=pickup_point.city,
            address=pickup_point.address,
            working_hours=pickup_point.working_hours,
            phone=pickup_point.phone,
            description=pickup_point.description,
            latitude=pickup_point.latitude,
            longitude=pickup_point.longitude,
            is_active=pickup_point.is_active,
            is_deleted=pickup_point.is_deleted,
            sort_order=pickup_point.sort_order,
            created_at=pickup_point.created_date,
            updated_at=pickup_point.updated_date,
        )
