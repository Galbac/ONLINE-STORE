from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.delivery_time_slot import DeliveryTimeSlot
from source.utils.delivery import get_weekday


class DeliveryTimeSlotRepository:
    async def get_by_id(self, *, session: AsyncSession, slot_id: int) -> DeliveryTimeSlot | None:
        result = await session.execute(select(DeliveryTimeSlot).where(DeliveryTimeSlot.id == slot_id))
        return result.scalar_one_or_none()

    async def get_by_day(
        self,
        *,
        session: AsyncSession,
        date_: date,
        delivery_type: str,
        pickup_point_id: int | None = None,
    ) -> list[DeliveryTimeSlot]:
        weekday = str(get_weekday(date_))
        statement = (
            select(DeliveryTimeSlot)
            .where(
                DeliveryTimeSlot.delivery_type == delivery_type,
                DeliveryTimeSlot.weekdays.like(f"%{weekday}%"),
            )
            .order_by(DeliveryTimeSlot.sort_order.asc(), DeliveryTimeSlot.start_time.asc())
        )
        if delivery_type == "pickup":
            statement = statement.where(
                or_(
                    DeliveryTimeSlot.pickup_point_id.is_(None),
                    DeliveryTimeSlot.pickup_point_id == pickup_point_id,
                ),
            )
        else:
            statement = statement.where(DeliveryTimeSlot.pickup_point_id.is_(None))

        result = await session.execute(statement)
        return list(result.scalars().all())
