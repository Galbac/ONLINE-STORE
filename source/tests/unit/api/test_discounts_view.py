from unittest.mock import AsyncMock

import pytest

from source.api.api_v1.views.discounts import (
    get_active_discounts,
    get_discount_products,
)
from source.schemas.pydantic.discount import (
    ActiveDiscountsResponse,
    DiscountProductsResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_get_active_discounts_success() -> None:
    service = AsyncMock()
    service.get_active_discounts.return_value = ActiveDiscountsResponse(
        items=[],
        total=0,
        limit=20,
        offset=0,
    )

    response = await unwrap(get_active_discounts)(
        limit=20,
        offset=0,
        type=None,
        only_with_products=True,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        discount_service=service,
        discount_cache_service=AsyncMock(),
        discount_repository=AsyncMock(),
    )

    assert response.total == 0
    assert len(response.items) == 0


@pytest.mark.asyncio
async def test_get_discount_products_success() -> None:
    service = AsyncMock()
    service.get_discounted_products.return_value = DiscountProductsResponse(
        items=[],
        total=0,
        page=1,
        limit=20,
        pages=1,
    )

    response = await unwrap(get_discount_products)(
        page=1,
        limit=20,
        category_id=None,
        in_stock=True,
        sort="discount_desc",
        session=AsyncMock(),
        redis_service=AsyncMock(),
        discount_service=service,
        discount_cache_service=AsyncMock(),
        product_repository=AsyncMock(),
    )

    assert response.total == 0
    assert response.page == 1
