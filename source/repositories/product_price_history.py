from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product_price_history import ProductPriceHistory


class ProductPriceHistoryRepository:
    async def bulk_create(
        self,
        *,
        session: AsyncSession,
        items: list[dict],
    ) -> list[ProductPriceHistory]:
        history_items = [ProductPriceHistory(**item) for item in items]
        session.add_all(history_items)
        await session.flush()
        for history_item in history_items:
            await session.refresh(history_item)
        return history_items
