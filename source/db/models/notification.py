from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class Notification(IdBigIntPkMixin, CreateUpdateMixin, Base):
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationLog(IdBigIntPkMixin, CreateUpdateMixin, Base):
    channel: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class NotificationSettings(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "notification_settings"

    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    email_from: Mapped[str | None] = mapped_column(String(255))
    email_sender_name: Mapped[str] = mapped_column(String(255), default="Супермаркет", server_default="Супермаркет", nullable=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    telegram_admin_chat_id: Mapped[str | None] = mapped_column(String(100))
    notify_admin_new_order: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notify_admin_payment_error: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notify_admin_1c_error: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notify_customer_order_created: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notify_customer_order_status: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notify_customer_payment: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notify_customer_delivery: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
