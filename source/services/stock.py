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
