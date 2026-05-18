from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.delivery_settings import DeliverySettings
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.pickup_point import PickupPointRepository
from source.schemas.pydantic.delivery import DeliveryOptionItemResponse, DeliveryOptionsResponse
from source.services.delivery_cache import DeliveryCacheService
from source.services.redis import RedisService


class DeliveryService:
    def calculate_delivery_price(self, *, delivery_type: str) -> Decimal:
        return Decimal("250.00") if delivery_type == "delivery" else Decimal("0")

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
