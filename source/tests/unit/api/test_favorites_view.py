from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.favorites import (
    add_to_favorites,
    get_favorites,
    remove_from_favorites,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import InactiveUserError
from source.errors.favorite import (
    FavoriteProductNotFoundError,
    FavoriteProductUnavailableError,
)
from source.schemas.pydantic.favorite import (
    FavoriteActionResponse,
    FavoritesResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=1, name="Клиент", role=UserRole.CUSTOMER, is_active=True, is_deleted=False)


# ---------------------------------------------------------
# GET /favorites
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_favorites_success(active_user):
    favorite_service = AsyncMock()
    favorite_service.get_favorites.return_value = FavoritesResponse(
        items=[],
        total=0,
        page=1,
        pages=1,
        limit=24,
    )

    response = await unwrap(get_favorites)(
        page=1,
        limit=24,
        current_user=active_user,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        favorite_service=favorite_service,
        favorite_cache_service=AsyncMock(),
        favorite_repository=AsyncMock(),
    )
    assert response.total == 0
    assert response.page == 1


@pytest.mark.asyncio
async def test_get_favorites_inactive_user(active_user):
    favorite_service = AsyncMock()
    favorite_service.get_favorites.side_effect = InactiveUserError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_favorites)(
            page=1,
            limit=24,
            current_user=active_user,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            favorite_service=favorite_service,
            favorite_cache_service=AsyncMock(),
            favorite_repository=AsyncMock(),
        )
    assert exc.value.status_code == 403


# ---------------------------------------------------------
# POST /favorites/{product_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_add_to_favorites_success(active_user):
    favorite_service = AsyncMock()
    favorite_service.add_to_favorites.return_value = FavoriteActionResponse(
        message="Товар добавлен в избранное",
        product_id=10,
    )
    commiter = AsyncMock()

    response = await unwrap(add_to_favorites)(
        product_id=10,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        favorite_service=favorite_service,
        favorite_cache_service=AsyncMock(),
        favorite_repository=AsyncMock(),
        product_repository=AsyncMock(),
    )
    assert response.product_id == 10
    assert response.message == "Товар добавлен в избранное"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_add_to_favorites_invalid_id(active_user):
    with pytest.raises(HTTPException) as exc:
        await unwrap(add_to_favorites)(
            product_id=0,
            current_user=active_user,
            session=AsyncMock(),
            commiter=AsyncMock(),
            redis_service=AsyncMock(),
            favorite_service=AsyncMock(),
            favorite_cache_service=AsyncMock(),
            favorite_repository=AsyncMock(),
            product_repository=AsyncMock(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_to_favorites_not_found(active_user):
    favorite_service = AsyncMock()
    favorite_service.add_to_favorites.side_effect = FavoriteProductNotFoundError
    commiter = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await unwrap(add_to_favorites)(
            product_id=999,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            favorite_service=favorite_service,
            favorite_cache_service=AsyncMock(),
            favorite_repository=AsyncMock(),
            product_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404
    assert commiter.rollback.called


@pytest.mark.asyncio
async def test_add_to_favorites_unavailable(active_user):
    favorite_service = AsyncMock()
    favorite_service.add_to_favorites.side_effect = FavoriteProductUnavailableError
    commiter = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await unwrap(add_to_favorites)(
            product_id=20,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            favorite_service=favorite_service,
            favorite_cache_service=AsyncMock(),
            favorite_repository=AsyncMock(),
            product_repository=AsyncMock(),
        )
    assert exc.value.status_code == 409
    assert commiter.rollback.called


# ---------------------------------------------------------
# DELETE /favorites/{product_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_from_favorites_success(active_user):
    favorite_service = AsyncMock()
    favorite_service.remove_from_favorites.return_value = FavoriteActionResponse(
        message="Товар удален из избранного",
        product_id=10,
    )
    commiter = AsyncMock()

    response = await unwrap(remove_from_favorites)(
        product_id=10,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        favorite_service=favorite_service,
        favorite_cache_service=AsyncMock(),
        favorite_repository=AsyncMock(),
    )
    assert response.product_id == 10
    assert response.message == "Товар удален из избранного"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_remove_from_favorites_invalid_id(active_user):
    with pytest.raises(HTTPException) as exc:
        await unwrap(remove_from_favorites)(
            product_id=-5,
            current_user=active_user,
            session=AsyncMock(),
            commiter=AsyncMock(),
            redis_service=AsyncMock(),
            favorite_service=AsyncMock(),
            favorite_cache_service=AsyncMock(),
            favorite_repository=AsyncMock(),
        )
    assert exc.value.status_code == 400
