from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.cart import Cart
from source.db.models.product import Product
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.schemas.pydantic.profile import CartItemResponse, CartResponse
from source.utils.cart import calculate_cart_totals


class CartService:
    async def get_or_create_cart(
        self,
        *,
        session: AsyncSession,
        cart_repository: CartRepository,
        user_id: int,
    ) -> Cart:
        return await cart_repository.get_or_create_by_user_id(session=session, user_id=user_id)

    async def clear_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        cart: Cart,
    ) -> None:
        await cart_item_repository.delete_by_cart_id(session=session, cart_id=cart.id)

    async def add_product_to_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        cart: Cart,
        product: Product,
        quantity: Decimal,
    ) -> None:
        await cart_item_repository.create_or_update(
            session=session,
            cart_id=cart.id,
            product=product,
            quantity=quantity,
        )

    async def recalculate_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        cart: Cart,
    ) -> CartResponse:
        items = await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id)
        total_price, discount_amount, final_price = calculate_cart_totals(items)
        return CartResponse(
            id=cart.id,
            items=[
                CartItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    name=item.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    price=item.price,
                    total_price=item.total_price,
                )
                for item in items
            ],
            total_price=total_price,
            discount_amount=discount_amount,
            final_price=final_price,
        )
