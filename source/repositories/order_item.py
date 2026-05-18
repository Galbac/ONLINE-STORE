from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.order_item import OrderItem


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
