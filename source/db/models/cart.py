from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class Cart(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __table_args__ = (UniqueConstraint("user_id", "store_id", name="uq_carts_user_store"),)

    store_id: Mapped[int | None] = mapped_column(ForeignKey("pickup_points.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id", ondelete="SET NULL"), index=True)
