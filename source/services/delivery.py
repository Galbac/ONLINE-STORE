from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.address import Address
from source.db.models.delivery_settings import DeliverySettings
from source.db.models.delivery_zone import DeliveryZone
from source.errors.delivery import (
    DeliveryAddressAccessDeniedError,
    DeliveryAddressNotFoundError,
    DeliveryDateInPastError,
    DeliveryDisabledError,
    DeliveryMinOrderAmountError,
    PickupDisabledError,
    PickupPointInactiveError,
    PickupPointNotFoundError,
)
from source.repositories.address import AddressRepository
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.delivery_time_slot import DeliveryTimeSlotRepository
from source.repositories.delivery_zone import DeliveryZoneRepository
from source.repositories.order import OrderRepository
from source.repositories.pickup_point import PickupPointRepository
from source.schemas.pydantic.delivery import (
    DeliveryCalculateRequest,
    DeliveryCalculateResponse,
    DeliveryOptionItemResponse,
    DeliveryOptionsResponse,
    DeliveryTimeSlotResponse,
    DeliveryTimeSlotsQueryParams,
    DeliveryTimeSlotsResponse,
    DeliveryZoneShortResponse,
    PickupPointDetailResponse,
    PickupPointListQueryParams,
    PickupPointListResponse,
    PickupPointResponse,
)
from source.services.delivery_cache import DeliveryCacheService
from source.services.redis import RedisService
from source.utils.delivery import normalize_address, normalize_amount, validate_future_date
from source.utils.query_hash import build_query_hash


class DeliveryService:
    def calculate_delivery_price(self, *, delivery_type: str) -> Decimal:
        return Decimal("250.00") if delivery_type == "delivery" else Decimal("0")

    async def calculate(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        delivery_cache_service: DeliveryCacheService,
        delivery_settings_repository: DeliverySettingsRepository,
        delivery_zone_service: "DeliveryZoneService",
        delivery_zone_repository: DeliveryZoneRepository,
        address_repository: AddressRepository,
        user_id: int | None,
        data: DeliveryCalculateRequest,
    ) -> DeliveryCalculateResponse:
        address = await self._resolve_address(
            session=session,
            address_repository=address_repository,
            user_id=user_id,
            data=data,
        )
        query_hash = build_query_hash(
            {
                **address,
                "order_amount": normalize_amount(data.order_amount),
            },
        )
        cached_response = await delivery_cache_service.get_calculation(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_response is not None:
            return cached_response

        delivery_settings = await delivery_settings_repository.get_settings(session=session)
        if delivery_settings is None:
            delivery_settings = self._default_settings()
        if not delivery_settings.delivery_enabled:
            raise DeliveryDisabledError
        if data.order_amount < delivery_settings.min_order_amount:
            raise DeliveryMinOrderAmountError

        zone = await delivery_zone_service.find_zone_by_address(
            session=session,
            city=address["city"],
            street=address["street"],
            house=address["house"],
            delivery_zone_repository=delivery_zone_repository,
        )
        if zone is None:
            response = DeliveryCalculateResponse(
                available=False,
                delivery_price=None,
                message="Доставка по этому адресу недоступна",
            )
        else:
            response = self._build_calculate_response(
                delivery_settings=delivery_settings,
                zone=zone,
                order_amount=data.order_amount,
            )

        await delivery_cache_service.set_calculation(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.delivery_calculate.cache_ttl_seconds,
        )
        return response

    async def get_options(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        delivery_cache_service: DeliveryCacheService,
        delivery_settings_repository: DeliverySettingsRepository,
        pickup_point_repository: PickupPointRepository,
    ) -> DeliveryOptionsResponse:
        cached_options = await delivery_cache_service.get_options(redis_service=redis_service)
        if cached_options is not None:
            return cached_options

        delivery_settings = await delivery_settings_repository.get_settings(session=session)
        if delivery_settings is None:
            delivery_settings = self._default_settings()
        has_pickup_points = await pickup_point_repository.has_active_points(session=session)

        response = self._build_options_response(
            delivery_settings=delivery_settings,
            has_pickup_points=has_pickup_points,
        )
        await delivery_cache_service.set_options(
            redis_service=redis_service,
            response=response,
            ttl_seconds=settings.delivery_options.cache_ttl_seconds,
        )
        return response

    async def get_pickup_points(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        delivery_cache_service: DeliveryCacheService,
        pickup_point_repository: PickupPointRepository,
        query: PickupPointListQueryParams,
    ) -> PickupPointListResponse:
        query_hash = build_query_hash(query.model_dump())
        cached_pickup_points = await delivery_cache_service.get_pickup_points(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_pickup_points is not None:
            return cached_pickup_points

        pickup_points = await pickup_point_repository.get_list(session=session, query=query)
        total = await pickup_point_repository.count(session=session, query=query)
        response = PickupPointListResponse(
            items=[
                self._build_pickup_point_response(pickup_point=pickup_point)
                for pickup_point in pickup_points
            ],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )
        await delivery_cache_service.set_pickup_points(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.delivery_pickup_points.list_cache_ttl_seconds,
        )
        return response

    async def get_pickup_point_by_id(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        delivery_cache_service: DeliveryCacheService,
        pickup_point_repository: PickupPointRepository,
        point_id: int,
    ) -> PickupPointDetailResponse:
        cached_pickup_point = await delivery_cache_service.get_pickup_point(
            redis_service=redis_service,
            point_id=point_id,
        )
        if cached_pickup_point is not None:
            return cached_pickup_point

        pickup_point = await pickup_point_repository.get_by_id(session=session, pickup_point_id=point_id)
        if pickup_point is None:
            raise PickupPointNotFoundError
        if not pickup_point.is_active:
            raise PickupPointInactiveError

        response = self._build_pickup_point_detail_response(pickup_point=pickup_point)
        await delivery_cache_service.set_pickup_point(
            redis_service=redis_service,
            point_id=point_id,
            response=response,
            ttl_seconds=settings.delivery_pickup_points.detail_cache_ttl_seconds,
        )
        return response

    def _build_options_response(
        self,
        *,
        delivery_settings: DeliverySettings | SimpleNamespace,
        has_pickup_points: bool,
    ) -> DeliveryOptionsResponse:
        return DeliveryOptionsResponse(
            delivery=DeliveryOptionItemResponse(
                enabled=delivery_settings.delivery_enabled,
                title=delivery_settings.delivery_title,
                description=delivery_settings.delivery_description,
                min_order_amount=delivery_settings.min_order_amount,
                base_price=delivery_settings.base_price,
                free_from_amount=delivery_settings.free_from_amount,
                has_time_slots=delivery_settings.has_time_slots,
            ),
            pickup=DeliveryOptionItemResponse(
                enabled=delivery_settings.pickup_enabled,
                title=delivery_settings.pickup_title,
                description=delivery_settings.pickup_description,
                price=delivery_settings.pickup_price,
                has_pickup_points=has_pickup_points,
            ),
        )

    def _build_calculate_response(
        self,
        *,
        delivery_settings: DeliverySettings | SimpleNamespace,
        zone: DeliveryZone,
        order_amount: Decimal,
    ) -> DeliveryCalculateResponse:
        free_from_amount = delivery_settings.free_from_amount
        amount_left_for_free_delivery = None
        delivery_price = zone.price if zone.price is not None else delivery_settings.base_price
        if free_from_amount is not None:
            amount_left_for_free_delivery = max(free_from_amount - order_amount, Decimal("0"))
            if order_amount >= free_from_amount:
                delivery_price = Decimal("0")

        return DeliveryCalculateResponse(
            available=True,
            delivery_price=delivery_price,
            free_delivery_from=free_from_amount,
            amount_left_for_free_delivery=amount_left_for_free_delivery,
            min_order_amount=delivery_settings.min_order_amount,
            zone=DeliveryZoneShortResponse(
                id=zone.id,
                name=zone.name,
            ),
            message="Доставка доступна",
        )

    def _build_pickup_point_response(self, *, pickup_point) -> PickupPointResponse:
        return PickupPointResponse(
            id=pickup_point.id,
            name=pickup_point.name,
            city=pickup_point.city,
            address=pickup_point.address,
            working_hours=pickup_point.working_hours,
            phone=pickup_point.phone,
            is_active=pickup_point.is_active,
            latitude=pickup_point.latitude,
            longitude=pickup_point.longitude,
        )

    def _build_pickup_point_detail_response(self, *, pickup_point) -> PickupPointDetailResponse:
        return PickupPointDetailResponse(
            **self._build_pickup_point_response(pickup_point=pickup_point).model_dump(),
            description=pickup_point.description,
        )

    async def _resolve_address(
        self,
        *,
        session: AsyncSession,
        address_repository: AddressRepository,
        user_id: int | None,
        data: DeliveryCalculateRequest,
    ) -> dict[str, str | None]:
        if data.address_id is None:
            return normalize_address(
                city=data.city or "",
                street=data.street or "",
                house=data.house or "",
                apartment=data.apartment,
            )

        if user_id is None:
            raise DeliveryAddressAccessDeniedError

        address = await address_repository.get_by_id(session=session, address_id=data.address_id)
        if address is None or address.is_deleted:
            raise DeliveryAddressNotFoundError
        if address.user_id != user_id:
            raise DeliveryAddressAccessDeniedError

        return self._normalize_model_address(address=address)

    def _normalize_model_address(self, *, address: Address) -> dict[str, str | None]:
        return normalize_address(
            city=address.city,
            street=address.street,
            house=address.house,
            apartment=address.apartment,
        )

    def _default_settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            delivery_enabled=True,
            delivery_title="Доставка",
            delivery_description="Доставка по городу",
            min_order_amount=Decimal("1000.00"),
            base_price=Decimal("250.00"),
            free_from_amount=Decimal("3000.00"),
            has_time_slots=True,
            pickup_enabled=True,
            pickup_title="Самовывоз",
            pickup_description="Можно забрать заказ из магазина",
            pickup_price=Decimal("0"),
        )


class DeliveryZoneService:
    async def find_zone_by_address(
        self,
        *,
        session: AsyncSession,
        city: str,
        street: str,
        house: str,
        delivery_zone_repository: DeliveryZoneRepository,
    ) -> DeliveryZone | None:
        return await delivery_zone_repository.find_by_city(session=session, city=city)


class DeliveryTimeSlotService:
    async def get_available_slots(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        delivery_cache_service: DeliveryCacheService,
        delivery_settings_repository: DeliverySettingsRepository,
        delivery_time_slot_repository: DeliveryTimeSlotRepository,
        pickup_point_repository: PickupPointRepository,
        order_repository: OrderRepository,
        query: DeliveryTimeSlotsQueryParams,
    ) -> DeliveryTimeSlotsResponse:
        try:
            validate_future_date(query.date)
        except ValueError as error:
            raise DeliveryDateInPastError from error

        delivery_settings = await delivery_settings_repository.get_settings(session=session)
        if delivery_settings is None:
            delivery_settings = DeliveryService()._default_settings()
        if query.delivery_type == "delivery" and not delivery_settings.delivery_enabled:
            raise DeliveryDisabledError
        if query.delivery_type == "pickup" and not delivery_settings.pickup_enabled:
            raise PickupDisabledError
        if query.delivery_type == "pickup" and query.pickup_point_id is not None:
            pickup_point = await pickup_point_repository.get_active_by_id(
                session=session,
                pickup_point_id=query.pickup_point_id,
            )
            if pickup_point is None:
                raise PickupPointNotFoundError

        query_hash = build_query_hash(query.model_dump())
        cached_time_slots = await delivery_cache_service.get_time_slots(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_time_slots is not None:
            return cached_time_slots

        slots = await delivery_time_slot_repository.get_by_day(
            session=session,
            date_=query.date,
            delivery_type=query.delivery_type,
            pickup_point_id=query.pickup_point_id,
        )
        response = DeliveryTimeSlotsResponse(
            date=query.date,
            delivery_type=query.delivery_type,
            items=[
                slot_response
                for slot in slots
                if (slot_response := await self._build_slot_response(
                    session=session,
                    order_repository=order_repository,
                    slot=slot,
                    query=query,
                )) is not None
            ],
        )
        await delivery_cache_service.set_time_slots(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.delivery_time_slots.cache_ttl_seconds,
        )
        return response

    async def check_slot_capacity(
        self,
        *,
        session: AsyncSession,
        order_repository: OrderRepository,
        delivery_date,
        delivery_type: str,
        delivery_time_slot_id: int,
        orders_limit: int,
        pickup_point_id: int | None = None,
    ) -> bool:
        orders_count = await order_repository.count_orders_by_time_slot(
            session=session,
            delivery_date=delivery_date,
            delivery_time_slot_id=delivery_time_slot_id,
            delivery_type=delivery_type,
            pickup_point_id=pickup_point_id,
        )
        return orders_count < orders_limit

    async def _build_slot_response(
        self,
        *,
        session: AsyncSession,
        order_repository: OrderRepository,
        slot,
        query: DeliveryTimeSlotsQueryParams,
    ) -> DeliveryTimeSlotResponse | None:
        if not slot.is_active or not self._slot_time_available(date_=query.date, end_time=slot.end_time):
            return None
        orders_count = await order_repository.count_orders_by_time_slot(
            session=session,
            delivery_date=query.date,
            delivery_time_slot_id=slot.id,
            delivery_type=query.delivery_type,
            pickup_point_id=query.pickup_point_id,
        )
        available = orders_count < slot.orders_limit
        return DeliveryTimeSlotResponse(
            id=slot.id,
            start_time=slot.start_time.strftime("%H:%M"),
            end_time=slot.end_time.strftime("%H:%M"),
            label=slot.label or f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')}",
            available=available,
            orders_limit=slot.orders_limit,
            orders_count=orders_count,
            reason=None if available else "Интервал заполнен",
        )

    def _slot_time_available(self, *, date_, end_time) -> bool:
        from datetime import datetime

        now = datetime.now(settings.tz)
        return date_ != now.date() or end_time > now.time()
