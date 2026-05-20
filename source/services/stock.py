from decimal import Decimal

from source.config.settings import settings
from source.db.models.product import Product
from source.errors.auth import (
    CartInsufficientStockError,
    CartPieceQuantityMustBeIntegerError,
    CartQuantityBelowMinimumError,
    CartQuantityStepError,
    OrderItemsNotFoundError,
    OrderUnavailableItemsError,
)
from source.utils.cart import is_quantity_valid_for_step


class StockService:
    def calculate_new_stock(
        self,
        *,
        current_stock: Decimal,
        quantity: Decimal,
        operation: str,
    ) -> Decimal:
        match operation:
            case "set":
                new_stock = quantity
            case "increase":
                new_stock = current_stock + quantity
            case "decrease":
                new_stock = current_stock - quantity
            case _:
                raise ValueError("Invalid stock operation")
        if new_stock < 0:
            raise ValueError("Stock quantity cannot be negative")
        return new_stock

    def validate_stock_quantity(self, *, product: Product, stock_quantity: Decimal) -> None:
        if stock_quantity < 0:
            raise ValueError("Stock quantity cannot be negative")
        if (
            settings.products.piece_stock_integer_required
            and product.product_type == "piece"
            and stock_quantity != stock_quantity.to_integral_value()
        ):
            raise ValueError("Stock quantity must be integer for piece products")

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

    async def validate_order_reserve(self, *, session, order_items: list, product_repository) -> None:
        if not order_items:
            raise OrderItemsNotFoundError

        products = await product_repository.get_by_ids(
            session=session,
            product_ids=[item.product_id for item in order_items],
        )
        products_by_id = {product.id: product for product in products}
        unavailable_items = []
        for item in order_items:
            product = products_by_id.get(item.product_id)
            if product is None or not product.is_active or product.is_deleted or not product.is_available:
                unavailable_items.append(
                    {
                        "product_id": item.product_id,
                        "name": item.product_name,
                        "reason": "Товар недоступен",
                        "requested_quantity": item.quantity,
                        "available_quantity": Decimal("0"),
                    },
                )
                continue
            if product.stock_quantity < 0:
                unavailable_items.append(
                    {
                        "product_id": product.id,
                        "name": product.name,
                        "reason": "Проблемы с резервом",
                        "requested_quantity": item.quantity,
                        "available_quantity": product.stock_quantity,
                    },
                )
        if unavailable_items:
            raise OrderUnavailableItemsError(unavailable_items)


class StockMovementService:
    async def create_log(
        self,
        *,
        session,
        stock_movement_repository,
        product_id: int,
        user_id: int,
        operation: str,
        quantity: Decimal,
        previous_stock_quantity: Decimal,
        new_stock_quantity: Decimal,
        low_stock_threshold: Decimal,
        reason: str | None,
    ):
        return await stock_movement_repository.create(
            session=session,
            product_id=product_id,
            user_id=user_id,
            operation=operation,
            quantity=quantity,
            previous_stock_quantity=previous_stock_quantity,
            new_stock_quantity=new_stock_quantity,
            low_stock_threshold=low_stock_threshold,
            reason=reason,
        )
