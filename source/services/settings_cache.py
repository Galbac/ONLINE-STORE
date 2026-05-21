from source.schemas.pydantic.settings import AdminSettingsResponse
from source.services.redis import RedisService


class SettingsCacheService:
    _admin_settings_key = "admin:settings"
    _public_settings_key = "public:settings"

    async def get_admin_settings(self, *, redis_service: RedisService) -> AdminSettingsResponse | None:
        cached_settings = await redis_service.get(self._admin_settings_key)
        if cached_settings is None:
            return None
        if isinstance(cached_settings, bytes):
            cached_settings = cached_settings.decode("utf-8")
        return AdminSettingsResponse.model_validate_json(cached_settings)

    async def set_admin_settings(
        self,
        *,
        redis_service: RedisService,
        response: AdminSettingsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._admin_settings_key,
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_admin_settings(self, *, redis_service: RedisService) -> None:
        await redis_service.delete(self._admin_settings_key)

    async def invalidate_public_settings(self, *, redis_service: RedisService) -> None:
        await redis_service.delete(self._public_settings_key)

    async def invalidate_settings(self, *, redis_service: RedisService) -> None:
        await self.invalidate_admin_settings(redis_service=redis_service)
        await self.invalidate_public_settings(redis_service=redis_service)
