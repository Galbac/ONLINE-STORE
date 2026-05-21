from decimal import Decimal

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class Order(IdBigIntPkMixin, CreateUpdateMixin, Base):
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"),
        index=True,
    )
    pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="SET NULL"),
        index=True,
    )
    delivery_zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="SET NULL"),
        index=True,
    )
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(50))
    payment_status: Mapped[str | None] = mapped_column(String(50), index=True)
    delivery_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    delivery_date: Mapped[date | None] = mapped_column(Date)
    delivery_time_slot_id: Mapped[int | None]
    delivery_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0", nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0", nullable=False)
    promo_discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0", nullable=False)
    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    internal_comment: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(String(50))
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    sync_status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending", nullable=False)
    external_1c_id: Mapped[str | None] = mapped_column(String(100), index=True)
    sync_error: Mapped[str | None] = mapped_column(Text)
    sync_error_code: Mapped[str | None] = mapped_column(String(100))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
