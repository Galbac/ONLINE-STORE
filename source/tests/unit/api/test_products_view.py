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

    with pytest.raises(ValueError, match="min_price must be less than or equal to max_price"):
        ProductSearchQueryParams(
            q="яблоки",
            min_price=Decimal("500"),
            max_price=Decimal("100"),
        )

