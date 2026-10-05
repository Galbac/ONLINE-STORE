from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product import Product
from source.schemas.pydantic.product import ProductShortResponse, ProductDetailResponse

from source.db.models.product_stock import ProductStock
from source.utils.product import build_stock_display, build_detailed_stock_display, calculate_discount_percent


class StoreCatalogService:
    async def get_stocks(self, *, session: AsyncSession, product_ids: list[int], store_id: int, for_update: bool = False) -> dict[int, ProductStock]:
        statement = select(ProductStock).where(
            ProductStock.product_id.in_(product_ids),
            ProductStock.pickup_point_id == store_id,
        ).order_by(ProductStock.product_id)
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return {stock.product_id: stock for stock in result.scalars().all()}

    async def scope_products(self, *, session: AsyncSession, products: list[Product], store_id: int | None, for_update: bool = False) -> list[Product] | list[SimpleNamespace]:
        if store_id is None or not products:
            return products
        stocks = await self.get_stocks(
            session=session, product_ids=[product.id for product in products],
            store_id=store_id, for_update=for_update,
        )
        scoped = []
        for product in products:
            stock = stocks.get(product.id)
            values = {column.key: getattr(product, column.key) for column in product.__mapper__.columns}
            values["stock_quantity"] = stock.stock_quantity if stock else Decimal("0")
            values["is_available"] = bool(stock and stock.stock_quantity > 0)
            if stock is not None and stock.price is not None:
                values["price"] = stock.price
                values["old_price"] = stock.old_price
            scoped.append(SimpleNamespace(**values))
        return scoped

    async def scope_responses(self, *, session: AsyncSession, items: list[ProductShortResponse] | list[ProductDetailResponse], store_id: int | None) -> list[ProductShortResponse] | list[ProductDetailResponse]:
        if store_id is None or not items:
            return items
        stocks = await self.get_stocks(
            session=session, product_ids=[item.id for item in items], store_id=store_id,
        )
        scoped = []
        for item in items:
            stock = stocks.get(item.id)
            quantity = stock.stock_quantity if stock else Decimal("0")
            price = stock.price if stock is not None and stock.price is not None else item.price
            old_price = stock.old_price if stock is not None and stock.price is not None else item.old_price
            scoped.append(item.model_copy(update={
                "price": price,
                "old_price": old_price,
                "discount_percent": calculate_discount_percent(price=price, old_price=old_price),
                "stock_quantity": quantity,
                "store_stock_quantity": quantity,
                "store_is_available": quantity > 0,
                "is_available": quantity > 0,
                "stock_display": build_detailed_stock_display(is_available=quantity > 0, stock_quantity=quantity, unit=item.unit) if isinstance(item, ProductDetailResponse) else build_stock_display(is_available=quantity > 0, stock_quantity=quantity),
            }))
        return scoped
