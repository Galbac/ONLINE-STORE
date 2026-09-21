from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.categories import (
    get_categories,
    get_category_by_id,
    get_category_by_slug,
    get_category_tree,
)
from source.errors.category import CategoryNotFoundError
from source.schemas.pydantic.category import (
    CategoryDetailResponse,
    CategoryListResponse,
    CategoryTreeResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def fake_category_detail():
    now = datetime.now(UTC)
    return CategoryDetailResponse(
        id=1,
        name="Молочные продукты",
        slug="molochnye-produkty",
        is_active=True,
        sort_order=1,
        products_count=25,
        breadcrumbs=[],
        children=[],
        created_date=now,
        updated_date=now,
    )


# ---------------------------------------------------------
# GET /categories/tree
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_category_tree_success():
    service = AsyncMock()
    service.get_category_tree.return_value = CategoryTreeResponse(
        items=[],
    )

    response = await unwrap(get_category_tree)(
        include_empty=False,
        max_depth=3,
        root_id=None,
        with_products_count=True,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        category_service=service,
        category_cache_service=AsyncMock(),
        category_repository=AsyncMock(),
    )

    assert len(response.items) == 0


@pytest.mark.asyncio
async def test_get_category_tree_not_found():
    service = AsyncMock()
    service.get_category_tree.side_effect = CategoryNotFoundError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_category_tree)(
            include_empty=False,
            max_depth=3,
            root_id=999,
            with_products_count=True,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            category_service=service,
            category_cache_service=AsyncMock(),
            category_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------
# GET /categories/{category_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_category_by_id_success(fake_category_detail):
    service = AsyncMock()
    service.get_category_by_id.return_value = fake_category_detail

    response = await unwrap(get_category_by_id)(
        category_id=1,
        with_children=True,
        with_breadcrumbs=True,
        with_products_count=True,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        category_service=service,
        category_cache_service=AsyncMock(),
        category_repository=AsyncMock(),
        product_repository=AsyncMock(),
    )

    assert response.id == 1
    assert response.name == "Молочные продукты"


@pytest.mark.asyncio
async def test_get_category_by_id_not_found():
    service = AsyncMock()
    service.get_category_by_id.side_effect = CategoryNotFoundError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_category_by_id)(
            category_id=999,
            with_children=True,
            with_breadcrumbs=True,
            with_products_count=True,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            category_service=service,
            category_cache_service=AsyncMock(),
            category_repository=AsyncMock(),
            product_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------
# GET /categories/slug/{slug}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_category_by_slug_success(fake_category_detail):
    service = AsyncMock()
    service.get_category_by_slug.return_value = fake_category_detail

    response = await unwrap(get_category_by_slug)(
        slug="molochnye-produkty",
        with_children=True,
        with_breadcrumbs=True,
        with_products_count=True,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        category_service=service,
        category_cache_service=AsyncMock(),
        category_repository=AsyncMock(),
        product_repository=AsyncMock(),
    )

    assert response.slug == "molochnye-produkty"


@pytest.mark.asyncio
async def test_get_category_by_slug_invalid():
    with pytest.raises(HTTPException) as exc:
        await unwrap(get_category_by_slug)(
            slug="!",  # невалидный slug
            with_children=True,
            with_breadcrumbs=True,
            with_products_count=True,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            category_service=AsyncMock(),
            category_cache_service=AsyncMock(),
            category_repository=AsyncMock(),
            product_repository=AsyncMock(),
        )
    assert exc.value.status_code == 400


# ---------------------------------------------------------
# GET /categories
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_categories_success():
    service = AsyncMock()
    service.get_categories.return_value = CategoryListResponse(
        items=[],
        total=0,
        limit=100,
        offset=0,
    )

    response = await unwrap(get_categories)(
        parent_id=None,
        only_root=False,
        include_empty=False,
        limit=100,
        offset=0,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        category_service=service,
        category_cache_service=AsyncMock(),
        category_repository=AsyncMock(),
    )

    assert response.total == 0
