from typing import Any

import redis.asyncio as aioredis


class RedisService:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> Any:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        await self._redis.set(key, value, ex=ttl_seconds)

    async def set_if_not_exists(self, key: str, value: str, *, ttl_seconds: int | None = None) -> bool:
        return bool(await self._redis.set(key, value, ex=ttl_seconds, nx=True))

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def delete_by_pattern(self, pattern: str) -> None:
        keys = [key async for key in self._redis.scan_iter(match=pattern)]
        if keys:
            await self._redis.delete(*keys)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def incr(self, key: str) -> int:
        return int(await self._redis.incr(key))

    async def expire(self, key: str, ttl_seconds: int) -> None:
        await self._redis.expire(key, ttl_seconds)


class RedisLockService:
    async def acquire(self, *, redis_service: RedisService, key: str, ttl_seconds: int) -> bool:
        return await redis_service.set_if_not_exists(key, "1", ttl_seconds=ttl_seconds)

    async def release(self, *, redis_service: RedisService, key: str) -> None:
        await redis_service.delete(key)
