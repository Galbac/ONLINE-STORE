from source.schemas.pydantic.notifications import AdminNotificationSettingsResponse
from source.services.redis import RedisService


class NotificationSettingsCacheService:
    _key = "admin:notifications:settings"

    async def get(self, *, redis_service: RedisService) -> AdminNotificationSettingsResponse | None:
        cached_settings = await redis_service.get(self._key)
        if cached_settings is None:
            return None
        if isinstance(cached_settings, bytes):
            cached_settings = cached_settings.decode("utf-8")
        return AdminNotificationSettingsResponse.model_validate_json(cached_settings)

    async def set(
        self,
        *,
        redis_service: RedisService,
        response: AdminNotificationSettingsResponse,
        ttl_seconds: int = 600,
    ) -> None:
        await redis_service.set(
            self._key,
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate(self, *, redis_service: RedisService) -> None:
        await redis_service.delete(self._key)
