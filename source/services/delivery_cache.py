from source.schemas.pydantic.delivery import DeliveryCalculateResponse, DeliveryOptionsResponse
from source.services.redis import RedisService


class DeliveryCacheService:
    _options_key = "delivery:options"
    _calculate_key_prefix = "delivery:calculate"

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
