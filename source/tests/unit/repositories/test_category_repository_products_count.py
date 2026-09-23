from unittest.mock import AsyncMock, MagicMock

import pytest

from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.category import CategoryListQueryParams


def test_category_repository_base_statement_filters_available_in_stock() -> None:
    repo = CategoryRepository()
    query = CategoryListQueryParams()
    stmt = repo._base_statement(query=query)
    sql_str = str(stmt)

    assert "products.is_available IS true" in sql_str
    assert "products.stock_quantity >" in sql_str
    assert "products.is_deleted IS false" in sql_str
    assert "products.is_active IS true" in sql_str


@pytest.mark.asyncio
async def test_product_repository_count_active_by_category_id_filters() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 7
    session.execute.return_value = mock_result

    repo = ProductRepository()
    count = await repo.count_active_by_category_id(session=session, category_id=102)

    assert count == 7
    assert session.execute.called
    stmt = session.execute.call_args[0][0]
    sql_str = str(stmt)

    assert "products.is_available IS true" in sql_str
    assert "products.stock_quantity >" in sql_str
    assert "products.is_deleted IS false" in sql_str
    assert "products.is_active IS true" in sql_str


@pytest.mark.asyncio
async def test_product_repository_count_active_grouped_by_category_filters() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [(102, 7)]
    session.execute.return_value = mock_result

    repo = ProductRepository()
    counts = await repo.count_active_grouped_by_category(session=session)

    assert counts == {102: 7}
    assert session.execute.called
    stmt = session.execute.call_args[0][0]
    sql_str = str(stmt)

    assert "products.is_available IS true" in sql_str
    assert "products.stock_quantity >" in sql_str
    assert "products.is_deleted IS false" in sql_str
    assert "products.is_active IS true" in sql_str
