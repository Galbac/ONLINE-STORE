from decimal import Decimal

import pytest
from fastapi import HTTPException

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.errors.favorite import FavoriteProductNotFoundError, FavoriteProductUnavailableError
from source.schemas.pydantic.favorite import FavoriteProductResponse, FavoritesQueryParams, FavoritesResponse
from source.services.favorite import FavoriteService
from source.services.favorite_cache import FavoriteCacheService
from source.utils.query_hash import build_query_hash


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted_patterns: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)


class FakeUser:
    id = 1
    is_active = True
    is_deleted = False


class FakeFavoriteRepository:
    def __init__(self, items=None) -> None:
        self.items = items if items is not None else [build_product(1), build_product(2, is_active=False), build_product(3, user_id=2)]
        self.get_calls = 0
        self.favorites: set[tuple[int, int]] = set()
        self.create_calls = 0
        self.deleted: list[tuple[int, int]] = []

    async def get_by_user_id(self, *, session, user_id: int, query: FavoritesQueryParams):
        self.get_calls += 1
        items = [item for item in self.items if item.user_id == user_id and item.is_active]
        return [item.response for item in items[query.offset : query.offset + query.limit]]

    async def count_by_user_id(self, *, session, user_id: int):
        return len([item for item in self.items if item.user_id == user_id and item.is_active])

    async def exists(self, *, session, user_id: int, product_id: int) -> bool:
        return (user_id, product_id) in self.favorites

    async def get_by_user_and_product(self, *, session, user_id: int, product_id: int):
        if (user_id, product_id) not in self.favorites:
            return None
        return type("Favorite", (), {"user_id": user_id, "product_id": product_id})()

    async def create(self, *, session, user_id: int, product_id: int):
        self.create_calls += 1
        self.favorites.add((user_id, product_id))
        return type("Favorite", (), {"user_id": user_id, "product_id": product_id})()

    async def delete(self, *, session, favorite) -> None:
        self.deleted.append((favorite.user_id, favorite.product_id))
        self.favorites.discard((favorite.user_id, favorite.product_id))


class FakeProductRepository:
    def __init__(self, products: dict[int, object] | None = None) -> None:
        self.products = products if products is not None else {
            55: build_product_model(product_id=55),
        }

    async def get_by_id(self, *, session, product_id: int):
        return self.products.get(product_id)


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


def build_product_model(
    *,
    product_id: int,
    is_active: bool = True,
    is_deleted: bool = False,
):
    return type(
        "Product",
        (),
        {
            "id": product_id,
            "is_active": is_active,
            "is_deleted": is_deleted,
        },
    )()


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


@pytest.mark.asyncio
async def test_add_to_favorites_success() -> None:
    repository = FakeFavoriteRepository()

    response = await FavoriteService().add_to_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        product_repository=FakeProductRepository(),
        user=FakeUser(),
        product_id=55,
    )

    assert response.message == "Товар добавлен в избранное"
    assert response.product_id == 55
    assert repository.favorites == {(1, 55)}


@pytest.mark.asyncio
async def test_add_to_favorites_duplicate_does_not_create_second_record() -> None:
    repository = FakeFavoriteRepository()
    repository.favorites.add((1, 55))

    response = await FavoriteService().add_to_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        product_repository=FakeProductRepository(),
        user=FakeUser(),
        product_id=55,
    )

    assert response.message == "Товар уже находится в избранном"
    assert repository.create_calls == 0


@pytest.mark.asyncio
async def test_add_to_favorites_product_not_found() -> None:
    with pytest.raises(FavoriteProductNotFoundError):
        await FavoriteService().add_to_favorites(
            session=object(),
            redis_service=FakeRedisService(),
            favorite_cache_service=FavoriteCacheService(),
            favorite_repository=FakeFavoriteRepository(),
            product_repository=FakeProductRepository({}),
            user=FakeUser(),
            product_id=55,
        )


@pytest.mark.asyncio
async def test_add_to_favorites_inactive_product() -> None:
    with pytest.raises(FavoriteProductUnavailableError):
        await FavoriteService().add_to_favorites(
            session=object(),
            redis_service=FakeRedisService(),
            favorite_cache_service=FavoriteCacheService(),
            favorite_repository=FakeFavoriteRepository(),
            product_repository=FakeProductRepository(
                {55: build_product_model(product_id=55, is_active=False)},
            ),
            user=FakeUser(),
            product_id=55,
        )


@pytest.mark.asyncio
async def test_add_to_favorites_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await FavoriteService().add_to_favorites(
        session=object(),
        redis_service=redis_service,
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=FakeFavoriteRepository(),
        product_repository=FakeProductRepository(),
        user=FakeUser(),
        product_id=55,
    )

    assert redis_service.deleted_patterns == ["favorites:1:*"]


@pytest.mark.asyncio
async def test_add_to_favorites_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_remove_from_favorites_success() -> None:
    repository = FakeFavoriteRepository()
    repository.favorites.add((1, 55))

    response = await FavoriteService().remove_from_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        user=FakeUser(),
        product_id=55,
    )

    assert response.message == "Товар удалён из избранного"
    assert response.product_id == 55
    assert repository.deleted == [(1, 55)]
    assert repository.favorites == set()


@pytest.mark.asyncio
async def test_remove_from_favorites_missing_item_is_success() -> None:
    repository = FakeFavoriteRepository()

    response = await FavoriteService().remove_from_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        user=FakeUser(),
        product_id=55,
    )

    assert response.message == "Товара не было в избранном"
    assert repository.deleted == []


@pytest.mark.asyncio
async def test_remove_from_favorites_does_not_touch_other_user_item() -> None:
    repository = FakeFavoriteRepository()
    repository.favorites.add((2, 55))

    response = await FavoriteService().remove_from_favorites(
        session=object(),
        redis_service=FakeRedisService(),
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        user=FakeUser(),
        product_id=55,
    )

    assert response.message == "Товара не было в избранном"
    assert repository.favorites == {(2, 55)}
    assert repository.deleted == []


@pytest.mark.asyncio
async def test_remove_from_favorites_invalidates_cache() -> None:
    redis_service = FakeRedisService()
    repository = FakeFavoriteRepository()
    repository.favorites.add((1, 55))

    await FavoriteService().remove_from_favorites(
        session=object(),
        redis_service=redis_service,
        favorite_cache_service=FavoriteCacheService(),
        favorite_repository=repository,
        user=FakeUser(),
        product_id=55,
    )

    assert redis_service.deleted_patterns == ["favorites:1:*"]


@pytest.mark.asyncio
async def test_remove_from_favorites_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401
