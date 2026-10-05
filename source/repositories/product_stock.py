from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product_stock import ProductStock


class ProductStockRepository:
    async def upsert_price(self, *, session, product_id, pickup_point_id, price, old_price):
        now = datetime.now(timezone.utc)
        statement = insert(ProductStock).values(
            product_id=product_id, pickup_point_id=pickup_point_id,
            price=price, old_price=old_price, price_updated_at=now,
        ).on_conflict_do_update(
            constraint="uq_product_pickup_point_stock",
            set_={"price": price, "old_price": old_price, "price_updated_at": now},
        )
        await session.execute(statement)

    async def get_by_product_and_point(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        pickup_point_id: int,
        for_update: bool = False,
    ) -> ProductStock | None:
        stmt = (
            select(ProductStock)
            .where(
                ProductStock.product_id == product_id,
                ProductStock.pickup_point_id == pickup_point_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_product_ids_and_point(
        self,
        *,
        session: AsyncSession,
        product_ids: list[int],
        pickup_point_id: int,
        for_update: bool = False,
    ) -> list[ProductStock]:
        if not product_ids:
            return []
        stmt = (
            select(ProductStock)
            .where(
                ProductStock.product_id.in_(product_ids),
                ProductStock.pickup_point_id == pickup_point_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> list[ProductStock]:
        stmt = (
            select(ProductStock)
            .where(ProductStock.product_id == product_id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_by_point_id(
        self,
        *,
        session: AsyncSession,
        pickup_point_id: int,
    ) -> list[ProductStock]:
        stmt = (
            select(ProductStock)
            .where(ProductStock.pickup_point_id == pickup_point_id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_stock(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        pickup_point_id: int,
        stock_quantity: Decimal,
        reserved_quantity: Decimal = Decimal("0"),
        low_stock_threshold: Decimal = Decimal("5"),
    ) -> ProductStock:
        now = datetime.now(timezone.utc)
        stmt = (
            insert(ProductStock)
            .values(
                product_id=product_id,
                pickup_point_id=pickup_point_id,
                stock_quantity=stock_quantity,
                reserved_quantity=reserved_quantity,
                low_stock_threshold=low_stock_threshold,
                stock_updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_product_pickup_point_stock",
                set_={
                    "stock_quantity": stock_quantity,
                    "stock_updated_at": now,
                },
            )
            .returning(ProductStock)
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    async def reserve_stock(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        pickup_point_id: int,
        quantity: Decimal,
    ) -> ProductStock:
        stock = await self.get_by_product_and_point(
            session=session,
            product_id=product_id,
            pickup_point_id=pickup_point_id,
            for_update=True,
        )
        if stock is None:
            raise ValueError(f"Stock for product {product_id} at point {pickup_point_id} not found")
        stock.stock_quantity -= quantity
        stock.reserved_quantity += quantity
        stock.stock_updated_at = datetime.now(timezone.utc)
        session.add(stock)
        return stock

    async def release_stock(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        pickup_point_id: int,
        quantity: Decimal,
    ) -> ProductStock:
        stock = await self.get_by_product_and_point(
            session=session,
            product_id=product_id,
            pickup_point_id=pickup_point_id,
            for_update=True,
        )
        if stock is None:
            raise ValueError(f"Stock for product {product_id} at point {pickup_point_id} not found")
        stock.stock_quantity += quantity
        stock.reserved_quantity = max(Decimal("0"), stock.reserved_quantity - quantity)
        stock.stock_updated_at = datetime.now(timezone.utc)
        session.add(stock)
        return stock
