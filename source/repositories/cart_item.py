from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.cart_item import CartItem
from source.db.models.product import Product


class CartItemRepository:
    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        cart_item_id: int,
    ) -> CartItem | None:
        result = await session.execute(select(CartItem).where(CartItem.id == cart_item_id))
        return result.scalar_one_or_none()

    async def get_by_cart_id(
        self,
        *,
        session: AsyncSession,
        cart_id: int,
    ) -> list[CartItem]:
        result = await session.execute(select(CartItem).where(CartItem.cart_id == cart_id))
        return list(result.scalars().all())

    async def create_or_update(
        self,
        *,
        session: AsyncSession,
        cart_id: int,
        product: Product,
        quantity: Decimal,
    ) -> CartItem:
        result = await session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id,
                CartItem.product_id == product.id,
            ),
        )
        cart_item = result.scalar_one_or_none()
        if cart_item is None:
            cart_item = CartItem(
                cart_id=cart_id,
                product_id=product.id,
                name=product.name,
                quantity=quantity,
                unit=product.unit,
                price=product.price,
                total_price=product.price * quantity,
            )
        else:
            cart_item.name = product.name
            cart_item.quantity += quantity
            cart_item.unit = product.unit
            cart_item.price = product.price
            cart_item.total_price = product.price * cart_item.quantity

        session.add(cart_item)
        await session.flush()
        await session.refresh(cart_item)
        return cart_item

    async def get_by_cart_and_product_id(
        self,
        *,
        session: AsyncSession,
        cart_id: int,
        product_id: int,
    ) -> CartItem | None:
        result = await session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id,
                CartItem.product_id == product_id,
            ),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        session: AsyncSession,
        cart_id: int,
        product: Product,
        quantity: Decimal,
    ) -> CartItem:
        cart_item = CartItem(
            cart_id=cart_id,
            product_id=product.id,
            name=product.name,
            quantity=quantity,
            unit=product.unit,
            price=product.price,
            total_price=product.price * quantity,
        )
        session.add(cart_item)
        await session.flush()
        await session.refresh(cart_item)
        return cart_item

    async def update_quantity(
        self,
        *,
        session: AsyncSession,
        cart_item: CartItem,
        product: Product,
        quantity: Decimal,
    ) -> CartItem:
        cart_item.name = product.name
        cart_item.quantity = quantity
        cart_item.unit = product.unit
        cart_item.price = product.price
        cart_item.total_price = product.price * quantity
        session.add(cart_item)
        await session.flush()
        await session.refresh(cart_item)
        return cart_item

    async def delete_by_cart_id(
        self,
        *,
        session: AsyncSession,
        cart_id: int,
    ) -> None:
        for cart_item in await self.get_by_cart_id(session=session, cart_id=cart_id):
            await session.delete(cart_item)
        await session.flush()

    async def delete(
        self,
        *,
        session: AsyncSession,
        cart_item: CartItem,
    ) -> None:
        await session.delete(cart_item)
        await session.flush()
