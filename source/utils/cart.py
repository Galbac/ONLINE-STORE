from decimal import Decimal


def validate_product_quantity(*, quantity: Decimal, available_quantity: Decimal, quantity_step: Decimal) -> Decimal:
    if available_quantity <= 0:
        return Decimal("0")

    quantity_to_add = min(quantity, available_quantity)
    if quantity_step <= 0:
        return quantity_to_add

    steps = quantity_to_add // quantity_step
    return steps * quantity_step


def calculate_cart_totals(items) -> tuple[Decimal, Decimal, Decimal]:
    total_price = sum((item.total_price for item in items), Decimal("0"))
    discount_amount = Decimal("0")
    final_price = total_price - discount_amount
    return total_price, discount_amount, final_price
