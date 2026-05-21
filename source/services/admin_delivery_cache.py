from source.schemas.pydantic.delivery import AdminDeliverySettingsResponse
from source.services.redis import RedisService


class AdminDeliveryCacheService:
    _settings_key = "admin:delivery:settings"

    async def get_settings(self, *, redis_service: RedisService) -> AdminDeliverySettingsResponse | None:
        cached_settings = await redis_service.get(self._settings_key)
        if cached_settings is None:
            return None
        if isinstance(cached_settings, bytes):
            cached_settings = cached_settings.decode("utf-8")
        return AdminDeliverySettingsResponse.model_validate_json(cached_settings)

    async def set_settings(
        self,
        *,
        redis_service: RedisService,
        response: AdminDeliverySettingsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._settings_key,
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_settings(self, *, redis_service: RedisService) -> None:
        await redis_service.delete(self._settings_key)
