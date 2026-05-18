from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class DeliveryTimeSlot(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "delivery_time_slots"

    delivery_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="CASCADE"),
        index=True,
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    label: Mapped[str | None] = mapped_column(String(50))
    weekdays: Mapped[str] = mapped_column(String(20), default="0,1,2,3,4,5,6", server_default="0,1,2,3,4,5,6", nullable=False)
    orders_limit: Mapped[int] = mapped_column(Integer, default=10, server_default="10", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
