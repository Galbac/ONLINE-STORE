from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class AdminAuditLog(IdBigIntPkMixin, CreateUpdateMixin, Base):
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    login: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    event: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)
