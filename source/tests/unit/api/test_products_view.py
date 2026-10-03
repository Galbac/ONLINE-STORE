import pytest
from fastapi import HTTPException

from source.api.api_v1.views.products import _normalize_required_search_query


def test_normalize_required_search_query_normalizes_q() -> None:
    assert _normalize_required_search_query("  ЯБЛОКИ   красные  ") == "яблоки красные"


def test_normalize_required_search_query_missing_q_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_required_search_query(None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Поисковый запрос обязателен"


def test_normalize_required_search_query_empty_q_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_required_search_query("   ")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Поисковый запрос обязателен"


def test_normalize_required_search_query_short_q_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_required_search_query("я")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Поисковый запрос слишком короткий"


def test_product_search_query_params_valid() -> None:
    from decimal import Decimal
    from source.schemas.pydantic.product import ProductSearchQueryParams

    params = ProductSearchQueryParams(
        q="яблоки",
        min_price=Decimal("100"),
        max_price=Decimal("500"),
        product_type="weight",
    )
    assert params.min_price == Decimal("100")
    assert params.max_price == Decimal("500")
    assert params.product_type == "weight"


def test_product_search_query_params_invalid_prices() -> None:
    from decimal import Decimal
    from source.schemas.pydantic.product import ProductSearchQueryParams

    with pytest.raises(ValueError, match=r"Минимальная цена \(min_price\) должна быть меньше или равна максимальной цене \(max_price\)"):
        ProductSearchQueryParams(
            q="яблоки",
            min_price=Decimal("500"),
            max_price=Decimal("100"),
        )


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_get_product_facets_view_success() -> None:
    from decimal import Decimal
    from unittest.mock import AsyncMock
    from source.api.api_v1.views.products import get_product_facets
    from source.schemas.pydantic.product import ProductFacetsResponse

    expected_facets = ProductFacetsResponse(
        has_discounts=True,
        discount_count=3,
        has_halal=False,
        halal_count=0,
        min_price=Decimal("50.00"),
        max_price=Decimal("400.00"),
        total_count=15,
    )
    product_service_mock = AsyncMock()
    product_service_mock.get_facets.return_value = expected_facets

    response = await unwrap(get_product_facets)(
        category_id=67,
        store_id=None,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        product_service=product_service_mock,
        product_cache_service=AsyncMock(),
        product_repository=AsyncMock(),
        category_repository=AsyncMock(),
    )

    assert response == expected_facets
    product_service_mock.get_facets.assert_awaited_once()

