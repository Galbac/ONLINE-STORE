from unittest.mock import AsyncMock, MagicMock

import pytest

from source.db.models.product import Product
from source.repositories.product import ProductRepository


@pytest.mark.asyncio
async def test_product_repository_get_by_ids_empty_list() -> None:
    session = AsyncMock()
    repo = ProductRepository()
    result = await repo.get_by_ids(session=session, product_ids=[])
    assert result == []
    assert not session.execute.called


@pytest.mark.asyncio
async def test_product_repository_get_by_ids_without_for_update() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        Product(id=1, name="Молоко"),
        Product(id=2, name="Сыр"),
    ]
    session.execute.return_value = mock_result

    repo = ProductRepository()
    products = await repo.get_by_ids(
        session=session,
        product_ids=[1, 2],
        for_update=False,
    )

    assert len(products) == 2
    assert session.execute.called
    stmt = session.execute.call_args[0][0]
    sql_str = str(stmt)
    assert "FOR UPDATE" not in sql_str.upper()


@pytest.mark.asyncio
async def test_product_repository_get_by_ids_with_for_update() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        Product(id=1, name="Молоко"),
    ]
    session.execute.return_value = mock_result

    repo = ProductRepository()
    products = await repo.get_by_ids(
        session=session,
        product_ids=[1],
        for_update=True,
    )

    assert len(products) == 1
    assert session.execute.called
    stmt = session.execute.call_args[0][0]
    sql_str = str(stmt)
    assert "FOR UPDATE" in sql_str.upper()
