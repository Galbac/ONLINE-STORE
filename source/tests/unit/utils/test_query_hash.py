from datetime import date
from decimal import Decimal

from source.utils.query_hash import build_query_hash


def test_build_query_hash_supports_decimal_values() -> None:
    query_hash = build_query_hash(
        {
            "page": 1,
            "limit": 24,
            "in_stock": True,
            "max_price": Decimal("1000"),
            "sort": "popular",
        },
    )

    assert isinstance(query_hash, str)
    assert len(query_hash) == 64


def test_build_query_hash_normalizes_nested_values() -> None:
    first_hash = build_query_hash(
        {
            "filters": {
                "max_price": Decimal("1000"),
                "empty": None,
                "dates": [date(2026, 5, 22)],
            },
        },
    )
    second_hash = build_query_hash(
        {
            "filters": {
                "dates": [date(2026, 5, 22)],
                "max_price": Decimal("1000"),
            },
        },
    )

    assert first_hash == second_hash
