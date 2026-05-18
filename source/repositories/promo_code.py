from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.promo_code import PromoCode, PromoCodeUsage


class PromoCodeRepository:
    async def get_by_id(self, *, session: AsyncSession, promo_code_id: int) -> PromoCode | None:
        result = await session.execute(select(PromoCode).where(PromoCode.id == promo_code_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, *, session: AsyncSession, code: str) -> PromoCode | None:
        result = await session.execute(select(PromoCode).where(PromoCode.code == code))
        return result.scalar_one_or_none()

    async def get_active_by_code(self, *, session: AsyncSession, code: str) -> PromoCode | None:
        result = await session.execute(select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True)))
        return result.scalar_one_or_none()


class PromoCodeUsageRepository:
    async def count_by_code(self, *, session: AsyncSession, promo_code_id: int) -> int:
        result = await session.execute(
            select(func.count(PromoCodeUsage.id)).where(PromoCodeUsage.promo_code_id == promo_code_id),
        )
        return result.scalar_one()

    async def count_by_user_and_code(self, *, session: AsyncSession, user_id: int, promo_code_id: int) -> int:
        result = await session.execute(
            select(func.count(PromoCodeUsage.id)).where(
                PromoCodeUsage.user_id == user_id,
                PromoCodeUsage.promo_code_id == promo_code_id,
            ),
        )
        return result.scalar_one()

    async def create(
        self,
        *,
        session: AsyncSession,
        promo_code_id: int,
        user_id: int,
        order_id: int | None = None,
        status: str = "reserved",
    ) -> PromoCodeUsage:
        usage = PromoCodeUsage(promo_code_id=promo_code_id, user_id=user_id, order_id=order_id, status=status)
        session.add(usage)
        await session.flush()
        await session.refresh(usage)
        return usage

    async def cancel_by_order_id(self, *, session: AsyncSession, order_id: int) -> None:
        result = await session.execute(select(PromoCodeUsage).where(PromoCodeUsage.order_id == order_id))
        usage = result.scalar_one_or_none()
        if usage is not None:
            usage.status = "cancelled"
            session.add(usage)
            await session.flush()
