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
    DeliveryDisabledError,
    DeliveryMinOrderAmountError,
)
from source.repositories.address import AddressRepository
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.delivery_zone import DeliveryZoneRepository
from source.repositories.pickup_point import PickupPointRepository
from source.schemas.pydantic.delivery import (
    DeliveryCalculateRequest,
    DeliveryCalculateResponse,
    DeliveryOptionItemResponse,
    DeliveryOptionsResponse,
    DeliveryZoneShortResponse,
)
from source.services.delivery_cache import DeliveryCacheService
from source.services.redis import RedisService
from source.utils.delivery import normalize_address, normalize_amount
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
