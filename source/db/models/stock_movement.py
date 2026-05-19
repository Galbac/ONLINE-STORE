from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class StockMovement(IdBigIntPkMixin, CreateUpdateMixin, Base):
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    operation: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    previous_stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    new_stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    low_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
