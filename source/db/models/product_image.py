from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class ProductImage(IdBigIntPkMixin, CreateUpdateMixin, Base):
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id", ondelete="SET NULL"), index=True)
    image_external_1c_id: Mapped[str | None] = mapped_column(String(100), index=True)
    external_url: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
