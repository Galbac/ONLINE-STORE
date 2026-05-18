from source.schemas.pydantic.delivery import (
    DeliveryCalculateResponse,
    DeliveryOptionsResponse,
    DeliveryTimeSlotsResponse,
    PickupPointDetailResponse,
    PickupPointListResponse,
)
from source.services.redis import RedisService


class DeliveryCacheService:
    _options_key = "delivery:options"
    _calculate_key_prefix = "delivery:calculate"
    _pickup_points_key_prefix = "delivery:pickup_points"
    _pickup_point_key_prefix = "delivery:pickup_point"
    _time_slots_key_prefix = "delivery:time_slots"

    async def get_options(self, *, redis_service: RedisService) -> DeliveryOptionsResponse | None:
        cached_options = await redis_service.get(self._options_key)
        if cached_options is None:
            return None
        if isinstance(cached_options, bytes):
            cached_options = cached_options.decode("utf-8")
        return DeliveryOptionsResponse.model_validate_json(cached_options)

    async def set_options(
        self,
        *,
        redis_service: RedisService,
        response: DeliveryOptionsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._options_key,
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_options(self, *, redis_service: RedisService) -> None:
        await redis_service.delete(self._options_key)

    async def get_calculation(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> DeliveryCalculateResponse | None:
        cached_calculation = await redis_service.get(self._build_calculate_key(query_hash=query_hash))
        if cached_calculation is None:
            return None
        if isinstance(cached_calculation, bytes):
            cached_calculation = cached_calculation.decode("utf-8")
        return DeliveryCalculateResponse.model_validate_json(cached_calculation)

    async def set_calculation(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: DeliveryCalculateResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._build_calculate_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    def _build_calculate_key(self, *, query_hash: str) -> str:
        return f"{self._calculate_key_prefix}:{query_hash}"

    async def get_pickup_points(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> PickupPointListResponse | None:
        cached_pickup_points = await redis_service.get(self._build_pickup_points_key(query_hash=query_hash))
        if cached_pickup_points is None:
            return None
        if isinstance(cached_pickup_points, bytes):
            cached_pickup_points = cached_pickup_points.decode("utf-8")
        return PickupPointListResponse.model_validate_json(cached_pickup_points)

    async def set_pickup_points(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: PickupPointListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._build_pickup_points_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_pickup_points(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern(f"{self._pickup_points_key_prefix}:*")

    async def get_pickup_point(
        self,
        *,
        redis_service: RedisService,
        point_id: int,
    ) -> PickupPointDetailResponse | None:
        cached_pickup_point = await redis_service.get(self._build_pickup_point_key(point_id=point_id))
        if cached_pickup_point is None:
            return None
        if isinstance(cached_pickup_point, bytes):
            cached_pickup_point = cached_pickup_point.decode("utf-8")
        return PickupPointDetailResponse.model_validate_json(cached_pickup_point)

    async def set_pickup_point(
        self,
        *,
        redis_service: RedisService,
        point_id: int,
        response: PickupPointDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._build_pickup_point_key(point_id=point_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_pickup_point(self, *, redis_service: RedisService, point_id: int) -> None:
        await redis_service.delete(self._build_pickup_point_key(point_id=point_id))
        await self.invalidate_pickup_points(redis_service=redis_service)

    async def get_time_slots(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> DeliveryTimeSlotsResponse | None:
        cached_time_slots = await redis_service.get(self._build_time_slots_key(query_hash=query_hash))
        if cached_time_slots is None:
            return None
        if isinstance(cached_time_slots, bytes):
            cached_time_slots = cached_time_slots.decode("utf-8")
        return DeliveryTimeSlotsResponse.model_validate_json(cached_time_slots)

    async def set_time_slots(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: DeliveryTimeSlotsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._build_time_slots_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_time_slots(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern(f"{self._time_slots_key_prefix}:*")

    def _build_pickup_points_key(self, *, query_hash: str) -> str:
        return f"{self._pickup_points_key_prefix}:{query_hash}"

    def _build_pickup_point_key(self, *, point_id: int) -> str:
        return f"{self._pickup_point_key_prefix}:{point_id}"

    def _build_time_slots_key(self, *, query_hash: str) -> str:
        return f"{self._time_slots_key_prefix}:{query_hash}"
