from source.schemas.pydantic.delivery import AdminDeliverySettingsResponse, AdminDeliveryZoneListResponse
from source.services.redis import RedisService


class AdminDeliveryCacheService:
    _settings_key = "admin:delivery:settings"

    def _zones_key(self, *, query_hash: str) -> str:
        return f"admin:delivery:zones:{query_hash}"

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

    async def get_zones(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> AdminDeliveryZoneListResponse | None:
        cached_zones = await redis_service.get(self._zones_key(query_hash=query_hash))
        if cached_zones is None:
            return None
        if isinstance(cached_zones, bytes):
            cached_zones = cached_zones.decode("utf-8")
        return AdminDeliveryZoneListResponse.model_validate_json(cached_zones)

    async def set_zones(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminDeliveryZoneListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._zones_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_zones(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:delivery:zones:*")
