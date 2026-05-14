from decimal import Decimal, ROUND_HALF_UP


def calculate_discount_percent(*, price: Decimal, old_price: Decimal | None) -> int:
    if old_price is None or old_price <= price or old_price <= 0:
        return 0
    discount = ((old_price - price) / old_price * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(discount)


def build_stock_display(*, is_available: bool, stock_quantity: Decimal) -> str:
    if not is_available or stock_quantity <= 0:
        return "Нет в наличии"
    return "В наличии"
