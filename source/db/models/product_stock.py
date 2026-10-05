from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class ProductStock(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "product_stocks"
    __table_args__ = (
        UniqueConstraint("product_id", "pickup_point_id", name="uq_product_pickup_point_stock"),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_store_price_nonnegative"),
        CheckConstraint("old_price IS NULL OR (price IS NOT NULL AND old_price >= price)", name="ck_store_old_price_valid"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    stock_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=0,
        server_default="0",
        nullable=False,
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=0,
        server_default="0",
        nullable=False,
    )
    low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=5,
        server_default="5",
        nullable=False,
    )
    stock_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product = relationship("Product", foreign_keys=[product_id])
    pickup_point = relationship("PickupPoint", foreign_keys=[pickup_point_id])
