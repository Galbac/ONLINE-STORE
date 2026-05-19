from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.order import Order
from source.db.models.order_item import OrderItem
from source.repositories.order import ACTIVE_ORDER_STATUSES


class OrderItemRepository:
    async def bulk_create(self, *, session: AsyncSession, items: list[dict]) -> list[OrderItem]:
        order_items = [OrderItem(**item) for item in items]
        session.add_all(order_items)
        await session.flush()
        return order_items

    async def get_by_order_id(
        self,
        *,
        session: AsyncSession,
        order_id: int,
    ) -> list[OrderItem]:
        result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
        return list(result.scalars().all())

    async def exists_active_order_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> bool:
        result = await session.execute(
            select(OrderItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.product_id == product_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES),
            )
            .limit(1),
        )
        return result.scalar_one_or_none() is not None
