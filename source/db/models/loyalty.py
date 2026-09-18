from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from source.db.models.base import Base
from source.db.models.mixins.create_update import CreateUpdateMixin
from source.db.models.mixins.id_int_pk import IdBigIntPkMixin


class LoyaltyAccount(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "loyalty_accounts"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    user = relationship("User", backref="loyalty_account")


class LoyaltyTransaction(IdBigIntPkMixin, CreateUpdateMixin, Base):
    __tablename__ = "loyalty_transactions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # positive for accrual, negative for write-off
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "accrual", "write_off"
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    user = relationship("User")
    order = relationship("Order")
