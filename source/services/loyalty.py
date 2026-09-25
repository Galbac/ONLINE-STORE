from sqlalchemy.ext.asyncio import AsyncSession

from source.common.commiter import Commiter
from source.db.models.user import User
from source.repositories.loyalty import LoyaltyRepository
from source.schemas.pydantic.loyalty import LoyaltyResponse, LoyaltyTransactionResponse


class LoyaltyService:
    async def get_loyalty_info(
        self,
        *,
        session: AsyncSession,
        loyalty_repository: LoyaltyRepository,
        user: User,
    ) -> LoyaltyResponse:
        account = await loyalty_repository.get_or_create_account(session=session, user_id=user.id)
        transactions = await loyalty_repository.get_transactions(session=session, user_id=user.id)

        level = "Золотой" if account.balance >= 1000 else "Серебряный" if account.balance >= 300 else "Базовый"
        cashback_percent = 7 if account.balance >= 1000 else 5 if account.balance >= 300 else 3

        return LoyaltyResponse(
            balance=account.balance,
            level=level,
            cashback_percent=cashback_percent,
            transactions=[LoyaltyTransactionResponse.model_validate(t) for t in transactions],
        )

    async def accrue_points(
        self,
        *,
        session: AsyncSession,
        loyalty_repository: LoyaltyRepository,
        commiter: Commiter,
        user_id: int,
        amount: int,
        description: str,
        order_id: int | None = None,
    ) -> None:
        if amount <= 0:
            return
        await loyalty_repository.add_transaction(
            session=session,
            user_id=user_id,
            amount=amount,
            transaction_type="accrual",
            description=description,
            order_id=order_id,
        )
        await commiter.commit()

    async def write_off_points(
        self,
        *,
        session: AsyncSession,
        loyalty_repository: LoyaltyRepository,
        commiter: Commiter,
        user_id: int,
        points_to_spend: int,
        order_id: int | None = None,
    ) -> int:
        if points_to_spend <= 0:
            return 0
        account = await loyalty_repository.get_or_create_account(session=session, user_id=user_id, for_update=True)
        actual_deduct = min(account.balance, points_to_spend)
        if actual_deduct <= 0:
            return 0

        await loyalty_repository.add_transaction(
            session=session,
            user_id=user_id,
            amount=-actual_deduct,
            transaction_type="write_off",
            description=f"Списание бонусов на заказ #{order_id}" if order_id else "Списание бонусов",
            order_id=order_id,
        )
        await commiter.commit()
        return actual_deduct
