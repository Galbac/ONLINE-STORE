from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.stock_movement import StockMovement


class StockMovementRepository:
    async def create(self, *, session: AsyncSession, **data) -> StockMovement:
        movement = StockMovement(**data)
        session.add(movement)
        await session.flush()
        await session.refresh(movement)
        return movement

    async def bulk_create(
        self,
        *,
        session: AsyncSession,
        items: list[dict],
    ) -> list[StockMovement]:
        movements = [StockMovement(**item) for item in items]
        session.add_all(movements)
        await session.flush()
        for movement in movements:
            await session.refresh(movement)
        return movements
