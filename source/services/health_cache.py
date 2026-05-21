from source.schemas.pydantic.health import HealthOneCResponse
from source.services.redis import RedisService


class HealthCacheService:
    _one_c_key = "health:1c"

    async def get_1c_status(self, *, redis_service: RedisService) -> HealthOneCResponse | None:
        cached_status = await redis_service.get(self._one_c_key)
        if cached_status is None:
            return None
        if isinstance(cached_status, bytes):
            cached_status = cached_status.decode("utf-8")
        return HealthOneCResponse.model_validate_json(cached_status)

    async def set_1c_status(
        self,
        *,
        redis_service: RedisService,
        response: HealthOneCResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._one_c_key,
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )
