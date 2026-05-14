from decimal import Decimal

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class Product(IdBigIntPkMixin, CreateUpdateMixin, Base):
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    preview_image_url: Mapped[str | None] = mapped_column(String(500))
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    product_type: Mapped[str] = mapped_column(String(20), default="piece", server_default="piece", nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, server_default="0", nullable=False)
    quantity_step: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1, server_default="1", nullable=False)
    popularity: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
