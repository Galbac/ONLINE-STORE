from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.cart import Cart


class CartRepository:
    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        cart_id: int,
    ) -> Cart | None:
        result = await session.execute(select(Cart).where(Cart.id == cart_id))
        return result.scalar_one_or_none()

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

    async def set_promo_code(
        self,
        *,
        session: AsyncSession,
        cart: Cart,
        promo_code_id: int | None,
    ) -> Cart:
        cart.promo_code_id = promo_code_id
        session.add(cart)
        await session.flush()
        await session.refresh(cart)
        return cart

    async def clear_promo_code(
        self,
        *,
        session: AsyncSession,
        cart: Cart,
    ) -> Cart:
        return await self.set_promo_code(session=session, cart=cart, promo_code_id=None)
