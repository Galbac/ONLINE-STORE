from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.loyalty import LoyaltyAccount, LoyaltyTransaction


class LoyaltyRepository:
    async def get_or_create_account(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> LoyaltyAccount:
        stmt = select(LoyaltyAccount).where(LoyaltyAccount.user_id == user_id)
        result = await session.execute(stmt)
        account = result.scalar_one_or_none()
        if account is None:
            account = LoyaltyAccount(user_id=user_id, balance=0)
            session.add(account)
            await session.flush()
            await session.refresh(account)
        return account

    async def get_transactions(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        limit: int = 50,
    ) -> list[LoyaltyTransaction]:
        stmt = (
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.user_id == user_id)
            .order_by(desc(LoyaltyTransaction.created_date))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def add_transaction(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        amount: int,
        transaction_type: str,
        description: str,
        order_id: int | None = None,
    ) -> tuple[LoyaltyAccount, LoyaltyTransaction]:
        account = await self.get_or_create_account(session=session, user_id=user_id)
        account.balance += amount
        if account.balance < 0:
            account.balance = 0

        transaction = LoyaltyTransaction(
            user_id=user_id,
            order_id=order_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
        )
        session.add(account)
        session.add(transaction)
        await session.flush()
        await session.refresh(account)
        await session.refresh(transaction)
        return account, transaction
