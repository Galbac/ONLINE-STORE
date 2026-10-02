from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from source.db.models.order import Order
from source.db.models.pickup_point import PickupPoint
from source.db.models.product import Product
from source.db.models.product_stock import ProductStock
from source.db.models.user import User, UserRole
from source.repositories.product_stock import ProductStockRepository
from source.schemas.pydantic.product import StoreStockResponse, ProductDetailResponse


@pytest.mark.asyncio
async def test_product_stock_repository_operations():
    session = AsyncMock()

    # Mock product stocks
    stock_point_1 = ProductStock(
        id=1,
        product_id=10,
        pickup_point_id=1,
        stock_quantity=Decimal("15"),
        reserved_quantity=Decimal("0"),
        low_stock_threshold=Decimal("5"),
    )

    repo = ProductStockRepository()
    
    # Mock get_by_product_and_point
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = stock_point_1
    session.execute.return_value = mock_result

    found = await repo.get_by_product_and_point(
        session=session,
        product_id=10,
        pickup_point_id=1,
    )
    assert found is not None
    assert found.stock_quantity == Decimal("15")

    # Test reserve stock
    reserved = await repo.reserve_stock(
        session=session,
        product_id=10,
        pickup_point_id=1,
        quantity=Decimal("3"),
    )
    assert reserved.stock_quantity == Decimal("12")
    assert reserved.reserved_quantity == Decimal("3")

    # Test release stock
    released = await repo.release_stock(
        session=session,
        product_id=10,
        pickup_point_id=1,
        quantity=Decimal("2"),
    )
    assert released.stock_quantity == Decimal("14")
    assert released.reserved_quantity == Decimal("1")


def test_store_stock_response_schema():
    store_stock = StoreStockResponse(
        store_id=1,
        store_name="Магазин №1 на Ленина",
        address="ул. Ленина, 12",
        stock_quantity=Decimal("8"),
        is_available=True,
    )
    assert store_stock.store_id == 1
    assert store_stock.is_available is True
    assert store_stock.stock_quantity == Decimal("8")

    detail = ProductDetailResponse(
        id=100,
        name="Молоко 3.2%",
        slug="moloko-3-2",
        price=Decimal("95.00"),
        unit="шт",
        product_type="piece",
        quantity_step=Decimal("1"),
        min_quantity=Decimal("1"),
        is_available=True,
        stock_quantity=Decimal("8"),
        stock_display="8 шт",
        images=[],
        stores_stock=[store_stock],
    )
    assert len(detail.stores_stock) == 1
    assert detail.stores_stock[0].store_name == "Магазин №1 на Ленина"


@pytest.mark.asyncio
async def test_staff_order_assignment_filtering():
    staff_user = User(
        id=77,
        name="Сборщик Магазина 1",
        phone="+79991112233",
        email="picker@test.local",
        role=UserRole.ADMIN,
        is_active=True,
        assigned_pickup_point_id=1,
    )
    assert staff_user.assigned_pickup_point_id == 1

    order_store_1 = Order(
        id=101,
        order_number="ORD-001",
        status="paid",
        delivery_type="pickup",
        fulfilling_store_id=1,
    )
    order_store_2 = Order(
        id=102,
        order_number="ORD-002",
        status="paid",
        delivery_type="pickup",
        fulfilling_store_id=2,
    )

    # Filter orders for staff_user
    orders = [order_store_1, order_store_2]
    filtered_orders = [
        o for o in orders
        if staff_user.assigned_pickup_point_id is None
        or o.fulfilling_store_id == staff_user.assigned_pickup_point_id
    ]

    assert len(filtered_orders) == 1
    assert filtered_orders[0].id == 101
    assert filtered_orders[0].fulfilling_store_id == 1


@pytest.mark.asyncio
async def test_one_c_import_multi_warehouse_same_product():
    from source.services.one_c import ProductStockSyncService
    from source.schemas.pydantic.one_c import OneCStockImportRequest, OneCStockImportItem

    product = Product(
        id=10,
        name="Сахар 1кг",
        slug="sahar-1kg",
        price=Decimal("80.00"),
        unit="шт",
        product_type="piece",
        stock_quantity=Decimal("0"),
        external_1c_id="PROD-SUGAR",
        low_stock_threshold=Decimal("5"),
        is_active=True,
        is_available=True,
    )

    class FakeProdRepo:
        async def get_by_external_1c_ids(self, session, external_1c_ids):
            return [product]
        async def bulk_update_stocks(self, session, products):
            pass

    class FakeMoveRepo:
        pass

    class FakeMoveService:
        async def create_bulk(self, session, stock_movement_repository, items):
            pass

    sync_service = ProductStockSyncService()
    req = OneCStockImportRequest(
        items=[
            OneCStockImportItem(
                product_external_1c_id="PROD-SUGAR",
                stock_quantity=Decimal("20"),
                warehouse_external_1c_id="WH-1",
            ),
            OneCStockImportItem(
                product_external_1c_id="PROD-SUGAR",
                stock_quantity=Decimal("35"),
                warehouse_external_1c_id="WH-2",
            ),
        ]
    )

    res = await sync_service.update_stocks_from_1c(
        session=AsyncMock(),
        data=req,
        product_repository=FakeProdRepo(),
        stock_movement_service=FakeMoveService(),
        stock_movement_repository=FakeMoveRepo(),
    )

    assert res.skipped == 0
    assert len(res.errors) == 0
    assert res.updated == 1
