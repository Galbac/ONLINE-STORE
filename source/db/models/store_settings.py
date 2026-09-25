from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class StoreSettings(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "store_settings"

    shop_name: Mapped[str] = mapped_column(String(255), default="Супермаркет", server_default="Супермаркет", nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), default="ИП Победа", server_default="ИП Победа")
    inn: Mapped[str | None] = mapped_column(String(12), default="000000000000", server_default="000000000000")
    ogrn: Mapped[str | None] = mapped_column(String(15), default="000000000000000", server_default="000000000000000")
    phone: Mapped[str | None] = mapped_column(String(32), default="+79990000000", server_default="+79990000000")
    email: Mapped[str | None] = mapped_column(String(255), default="info@example.com", server_default="info@example.com")
    address: Mapped[str | None] = mapped_column(String(500), default="ул. Победы, 87А, Кизляр", server_default="ул. Победы, 87А, Кизляр")
    working_hours: Mapped[str | None] = mapped_column(String(255), default="Пн-Вс 09:00-22:00", server_default="Пн-Вс 09:00-22:00")
    schedule: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    online_payment_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    pay_on_delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    promo_codes_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    referral_program_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    loyalty_program_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    privacy_policy_url: Mapped[str | None] = mapped_column(String(500), default="/privacy", server_default="/privacy")
    user_agreement_url: Mapped[str | None] = mapped_column(String(500), default="/offer", server_default="/offer")
    personal_data_consent_url: Mapped[str | None] = mapped_column(String(500), default="/personal-data-consent", server_default="/personal-data-consent")
