from datetime import datetime

from sqlalchemy.dialects import postgresql

from source.repositories.product import ProductRepository
from source.schemas.pydantic.product import ProductPopularQueryParams


def test_popular_products_rank_recent_valid_orders_for_selected_store() -> None:
    statement = ProductRepository()._popular_statement(
        query=ProductPopularQueryParams(period_days=14, store_id=3),
        category_ids=None,
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "count(distinct(order_items.order_id))" in sql
    assert "sum(order_items.quantity)" in sql
    assert "orders.created_date >=" in sql
    assert "orders.status NOT IN" in sql
    assert "coalesce(orders.fulfilling_store_id, orders.pickup_point_id)" in sql
    assert "ORDER BY coalesce(anon_1.order_count" in sql
    assert "products.popularity" not in sql.rsplit("ORDER BY", maxsplit=1)[-1]
    assert 3 in compiled.params.values()
    assert any(isinstance(value, datetime) for value in compiled.params.values())
