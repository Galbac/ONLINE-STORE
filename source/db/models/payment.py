from decimal import Decimal

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class Payment(IdBigIntPkMixin, CreateUpdateMixin, Base):
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB", nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50))
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), index=True)
    payment_url: Mapped[str | None] = mapped_column(String(500))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_status: Mapped[str | None] = mapped_column(String(50))
