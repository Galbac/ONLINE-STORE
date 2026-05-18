from decimal import Decimal


def normalize_promo_code(code: str) -> str:
    return code.strip().upper()


def calculate_promo_discount(*, discount_type: str, discount_value: Decimal, amount: Decimal) -> Decimal:
    if discount_type == "percent":
        return amount * discount_value / Decimal("100")
    return min(discount_value, amount)
