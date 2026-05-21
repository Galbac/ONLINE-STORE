from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class DeliverySettings(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "delivery_settings"

    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    delivery_title: Mapped[str] = mapped_column(String(255), default="Доставка", server_default="Доставка", nullable=False)
    delivery_description: Mapped[str] = mapped_column(
        Text,
        default="Доставка по городу",
        server_default="Доставка по городу",
        nullable=False,
    )
    min_order_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("1000.00"),
        server_default="1000.00",
        nullable=False,
    )
    base_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("250.00"),
        server_default="250.00",
        nullable=False,
    )
    free_from_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        default=Decimal("3000.00"),
        server_default="3000.00",
    )
    has_time_slots: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    pickup_title: Mapped[str] = mapped_column(String(255), default="Самовывоз", server_default="Самовывоз", nullable=False)
    pickup_description: Mapped[str] = mapped_column(
        Text,
        default="Можно забрать заказ из магазина",
        server_default="Можно забрать заказ из магазина",
        nullable=False,
    )
    pickup_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), server_default="0", nullable=False)
    default_city: Mapped[str] = mapped_column(String(100), default="Москва", server_default="Москва", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB", nullable=False)
