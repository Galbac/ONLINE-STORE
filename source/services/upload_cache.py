from source.schemas.pydantic.upload import UploadFileResponse
from source.services.redis import RedisService


class UploadCacheService:
    def _detail_key(self, *, file_id: int) -> str:
        return f"uploads:detail:{file_id}"

    async def get_detail(self, *, redis_service: RedisService, file_id: int) -> UploadFileResponse | None:
        cached = await redis_service.get(self._detail_key(file_id=file_id))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        return UploadFileResponse.model_validate_json(cached)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        file_id: int,
        response: UploadFileResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(file_id=file_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_detail(self, *, redis_service: RedisService, file_id: int) -> None:
        await redis_service.delete(self._detail_key(file_id=file_id))
