from typing import Any

import redis.asyncio as aioredis


class RedisService:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> Any:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        await self._redis.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def incr(self, key: str) -> int:
        return int(await self._redis.incr(key))

    async def expire(self, key: str, ttl_seconds: int) -> None:
        await self._redis.expire(key, ttl_seconds)
