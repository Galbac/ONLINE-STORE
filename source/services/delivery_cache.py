from source.schemas.pydantic.delivery import DeliveryOptionsResponse
from source.services.redis import RedisService


class DeliveryCacheService:
    _options_key = "delivery:options"

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
