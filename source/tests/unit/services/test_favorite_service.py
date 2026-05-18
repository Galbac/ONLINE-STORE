from decimal import Decimal

import pytest

from source.config.settings import settings
from source.schemas.pydantic.favorite import FavoriteProductResponse, FavoritesQueryParams, FavoritesResponse
from source.services.favorite import FavoriteService
from source.services.favorite_cache import FavoriteCacheService
from source.utils.query_hash import build_query_hash


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        pass


class FakeUser:
    id = 1
    is_active = True
    is_deleted = False


class FakeFavoriteRepository:
    def __init__(self, items=None) -> None:
        self.items = items if items is not None else [build_product(1), build_product(2, is_active=False), build_product(3, user_id=2)]
        self.get_calls = 0

    async def get_by_user_id(self, *, session, user_id: int, query: FavoritesQueryParams):
        self.get_calls += 1
        items = [item for item in self.items if item.user_id == user_id and item.is_active]
        return [item.response for item in items[query.offset : query.offset + query.limit]]

    async def count_by_user_id(self, *, session, user_id: int):
        return len([item for item in self.items if item.user_id == user_id and item.is_active])


def build_product(product_id: int, *, user_id: int = 1, is_active: bool = True):
    response = FavoriteProductResponse(
        id=product_id,
        name=f"Товар {product_id}",
        slug=f"product-{product_id}",
        price=Decimal("100.00"),
        old_price=None,
        discount_percent=None,
        unit="pcs",
        product_type="piece",
        is_available=True,
        stock_display="В наличии",
    )
    return type("FavoriteItem", (), {"user_id": user_id, "is_active": is_active, "response": response})()


@pytest.mark.asyncio
async def test_get_favorites_success_filters_user_and_inactive() -> None:
    response = await FavoriteService().get_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=FakeFavoriteRepository(),
        user=FakeUser(),
        query=FavoritesQueryParams(),
    )

    assert response.total == 1
    assert response.items[0].id == 1


@pytest.mark.asyncio
async def test_get_favorites_empty() -> None:
    response = await FavoriteService().get_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=FakeFavoriteRepository([]),
        user=FakeUser(),
        query=FavoritesQueryParams(),
    )

    assert response.total == 0
    assert response.items == []


@pytest.mark.asyncio
async def test_get_favorites_pagination_and_cache_set() -> None:
    redis_service = FakeRedisService()
    query = FavoritesQueryParams(page=2, limit=1)
    response = await FavoriteService().get_favorites(
        session=object(),
        redis_service=redis_service,
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=FakeFavoriteRepository([build_product(1), build_product(2)]),
        user=FakeUser(),
        query=query,
    )

    assert response.items[0].id == 2
    assert redis_service.ttls[f"favorites:1:{build_query_hash(query.model_dump())}"] == settings.favorites.cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_favorites_from_cache() -> None:
    redis_service = FakeRedisService()
    query = FavoritesQueryParams()
    cached = FavoritesResponse.build(items=[], total=0, page=1, limit=24)
    redis_service.values[f"favorites:1:{build_query_hash(query.model_dump())}"] = cached.model_dump_json()
    repository = FakeFavoriteRepository()

    response = await FavoriteService().get_favorites(
        session=object(),
        redis_service=redis_service,
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        user=FakeUser(),
        query=query,
    )

    assert response == cached
    assert repository.get_calls == 0
