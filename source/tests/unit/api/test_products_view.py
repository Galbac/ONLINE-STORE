import pytest
from fastapi import HTTPException, Response

from source.api.api_v1.views.products import _normalize_required_search_query
from source.api.api_v1.views.products import _is_trackable_search_query


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


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("овощи", True),
        ("сыр 45%", True),
        ("", False),
        ("1", False),
        ("89123456789", False),
        ("молоко 89123456789", False),
        ("name@example.com", False),
        ("x" * 81, False),
    ],
)
def test_is_trackable_search_query(query: str, expected: bool) -> None:
    assert _is_trackable_search_query(query) is expected


@pytest.mark.asyncio
async def test_track_search_query_records_normalized_query() -> None:
    from unittest.mock import AsyncMock
    from source.api.api_v1.views.products import track_search_query
    from source.schemas.pydantic.search_query import SearchQueryTrackRequest

    repository = AsyncMock()
    response = await unwrap(track_search_query)(
        payload=SearchQueryTrackRequest(query="  ОВОЩИ   свежие "),
        session=AsyncMock(),
        search_query_stat_repository=repository,
    )

    assert response.tracked is True
    repository.track.assert_awaited_once()
    assert repository.track.await_args.kwargs["query"] == "овощи свежие"


@pytest.mark.asyncio
async def test_track_search_query_does_not_store_personal_data() -> None:
    from unittest.mock import AsyncMock
    from source.api.api_v1.views.products import track_search_query
    from source.schemas.pydantic.search_query import SearchQueryTrackRequest

    repository = AsyncMock()
    response = await unwrap(track_search_query)(
        payload=SearchQueryTrackRequest(query="user@example.com"),
        session=AsyncMock(),
        search_query_stat_repository=repository,
    )

    assert response.tracked is False
    repository.track.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_popular_searches_returns_aggregated_queries() -> None:
    from unittest.mock import AsyncMock
    from source.api.api_v1.views.products import get_popular_searches

    repository = AsyncMock()
    repository.get_popular.return_value = ["овощи", "молоко"]
    headers = Response()
    response = await unwrap(get_popular_searches)(
        limit=8,
        response=headers,
        session=AsyncMock(),
        search_query_stat_repository=repository,
    )

    assert response == ["овощи", "молоко"]
    assert headers.headers["Cache-Control"] == "public, max-age=300"
    repository.get_popular.assert_awaited_once()


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
