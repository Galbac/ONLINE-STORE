from decimal import Decimal

from source.db.models.product import Product
from source.errors.auth import (
    CartInsufficientStockError,
    CartPieceQuantityMustBeIntegerError,
    CartQuantityBelowMinimumError,
    CartQuantityStepError,
)
from source.utils.cart import is_quantity_valid_for_step


class StockService:
    def validate_quantity(self, *, product: Product, quantity: Decimal) -> None:
        if product.product_type == "piece" and quantity != quantity.to_integral_value():
            raise CartPieceQuantityMustBeIntegerError
        if quantity < product.min_quantity:
            raise CartQuantityBelowMinimumError
        if not is_quantity_valid_for_step(quantity=quantity, quantity_step=product.quantity_step):
            raise CartQuantityStepError

    def check_available_stock(self, *, product: Product, quantity: Decimal) -> None:
        if product.stock_quantity < quantity:
            raise CartInsufficientStockError

    def validate_order_items(self, *, cart_items: list, products_by_id: dict[int, Product]) -> list[dict]:
        unavailable_items: list[dict] = []
        for item in cart_items:
            product = products_by_id.get(item.product_id)
            if product is None or not product.is_active or product.is_deleted or not product.is_available:
                unavailable_items.append(
                    {
                        "product_id": item.product_id,
                        "name": item.name,
                        "reason": "Товар недоступен",
                        "requested_quantity": item.quantity,
                        "available_quantity": Decimal("0"),
                    },
                )
                continue
            if product.stock_quantity < item.quantity:
                unavailable_items.append(
                    {
                        "product_id": product.id,
                        "name": product.name,
                        "reason": "Недостаточно остатка",
                        "requested_quantity": item.quantity,
                        "available_quantity": product.stock_quantity,
                    },
                )
        return unavailable_items

    async def reserve_items(self, *, products_by_id: dict[int, Product], cart_items: list) -> None:
        for item in cart_items:
            product = products_by_id[item.product_id]
            product.stock_quantity -= item.quantity

    async def release_reserved_items(self, *, product_repository, session, products_by_id: dict[int, Product], order_items: list):
        return await product_repository.release_stock(
            session=session,
            products_by_id=products_by_id,
            order_items=order_items,
        )
