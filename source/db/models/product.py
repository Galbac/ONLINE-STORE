from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class Product(IdBigIntPkMixin, CreateUpdateMixin, Base):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, server_default="0", nullable=False)
    quantity_step: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1, server_default="1", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
