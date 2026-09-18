from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.stock_alert import StockAlert


class StockAlertRepository:
    async def create_alert(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        user_id: int | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> StockAlert:
        alert = StockAlert(
            product_id=product_id,
            user_id=user_id,
            email=email,
            phone=phone,
            is_notified=False,
        )
        session.add(alert)
        await session.flush()
        await session.refresh(alert)
        return alert

    async def get_pending_alerts(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> list[StockAlert]:
        stmt = (
            select(StockAlert)
            .where(
                StockAlert.product_id == product_id,
                StockAlert.is_notified.is_(False),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def mark_notified(
        self,
        *,
        session: AsyncSession,
        alert_id: int,
    ) -> None:
        stmt = select(StockAlert).where(StockAlert.id == alert_id)
        result = await session.execute(stmt)
        alert = result.scalar_one_or_none()
        if alert is not None:
            alert.is_notified = True
            session.add(alert)
            await session.flush()
