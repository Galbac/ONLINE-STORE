from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class StoreSettings(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "store_settings"

    shop_name: Mapped[str] = mapped_column(String(255), default="Супермаркет", server_default="Супермаркет", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), default="+79990000000", server_default="+79990000000")
    email: Mapped[str | None] = mapped_column(String(255), default="info@example.com", server_default="info@example.com")
    address: Mapped[str | None] = mapped_column(String(500), default="Москва, ул. Тверская, 10", server_default="Москва, ул. Тверская, 10")
    working_hours: Mapped[str | None] = mapped_column(String(255), default="Пн-Вс 09:00-22:00", server_default="Пн-Вс 09:00-22:00")
    online_payment_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    pay_on_delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
