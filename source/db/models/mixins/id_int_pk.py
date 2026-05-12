from uuid6 import UUID, uuid7

from sqlalchemy import BigInteger, Identity
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class IdBigIntPkMixin:

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )


class UUIDPkMixin:

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        unique=True,
        nullable=False,
    )
