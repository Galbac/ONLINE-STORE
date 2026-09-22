from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class LegalDocument(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "legal_documents"

    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
