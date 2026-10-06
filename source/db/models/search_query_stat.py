from datetime import date

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from source.db.models.base import Base
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class SearchQueryStat(IdBigIntPkMixin, Base):
    __tablename__ = "search_query_stats"
    __table_args__ = (
        UniqueConstraint("search_date", "query", name="uq_search_query_stats_date_query"),
    )

    search_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    query: Mapped[str] = mapped_column(String(80), nullable=False)
    search_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
