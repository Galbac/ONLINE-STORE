from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from source.config.settings import settings


class CreateUpdateMixin:

    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(settings.tz),
        server_default=func.timezone("Europe/Moscow", func.now()),
    )
    updated_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(settings.tz),
        onupdate=lambda: datetime.now(settings.tz),
        server_default=func.timezone("Europe/Moscow", func.now()),
    )
