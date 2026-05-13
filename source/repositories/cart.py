from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.cart import Cart


class CartRepository:
    async def get_or_create_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> Cart:
        result = await session.execute(select(Cart).where(Cart.user_id == user_id))
        cart = result.scalar_one_or_none()
        if cart is not None:
            return cart

        cart = Cart(user_id=user_id)
        session.add(cart)
        await session.flush()
        await session.refresh(cart)
        return cart
