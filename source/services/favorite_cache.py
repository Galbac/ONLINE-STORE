from source.schemas.pydantic.favorite import FavoritesResponse
from source.services.redis import RedisService


class FavoriteCacheService:
    def _key(self, *, user_id: int, query_hash: str) -> str:
        return f"favorites:{user_id}:{query_hash}"

    async def get(self, *, redis_service: RedisService, user_id: int, query_hash: str) -> FavoritesResponse | None:
        cached = await redis_service.get(self._key(user_id=user_id, query_hash=query_hash))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        return FavoritesResponse.model_validate_json(cached)

    async def set(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
        response: FavoritesResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._key(user_id=user_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate(self, *, redis_service: RedisService, user_id: int) -> None:
        await redis_service.delete_by_pattern(f"favorites:{user_id}:*")
