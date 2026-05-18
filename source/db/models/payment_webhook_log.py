from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class PaymentWebhookLog(IdBigIntPkMixin, CreateUpdateMixin, Base):
    provider_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(100))
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), index=True)
    payment_id: Mapped[int | None]
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500))
