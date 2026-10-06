from types import SimpleNamespace

import pytest

from source.services.product_cache import ProductCacheService


class RecordingRedis:
    def __init__(self) -> None:
        self.deleted_patterns: list[str] = []

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)

    async def delete(self, key: str) -> None:
        return None


@pytest.mark.asyncio
async def test_stock_changes_invalidate_popular_product_cache() -> None:
    redis = RecordingRedis()

    await ProductCacheService().invalidate_by_stock_changes(
        redis_service=redis,
        products=[SimpleNamespace(id=12, slug="milk")],
    )

    assert "products:popular:*" in redis.deleted_patterns
