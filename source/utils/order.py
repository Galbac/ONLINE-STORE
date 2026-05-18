from decimal import Decimal


def normalize_phone(phone: str) -> str:
    normalized = "".join(char for char in phone.strip() if char.isdigit() or char == "+")
    if normalized.startswith("8") and len(normalized) == 11:
        return f"+7{normalized[1:]}"
    if normalized.startswith("7") and len(normalized) == 11:
        return f"+{normalized}"
    return normalized


def validate_delivery_type(value: str) -> str:
    if value not in {"delivery", "pickup"}:
        raise ValueError("Неверный тип доставки")
    return value


def validate_payment_method(value: str) -> str:
    if value not in {"online", "on_delivery"}:
        raise ValueError("Неверный способ оплаты")
    return value


def validate_order_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def validate_payment_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def calculate_order_totals(*, subtotal: Decimal, discount_amount: Decimal, promo_discount_amount: Decimal, delivery_price: Decimal) -> Decimal:
    final_price = subtotal - discount_amount - promo_discount_amount + delivery_price
    return max(final_price, Decimal("0"))


def generate_order_number(*, prefix: str, order_id: int) -> str:
    return f"{prefix}-{order_id:06d}"


def is_order_cancel_allowed(*, status: str, allowed_statuses: set[str]) -> bool:
    return status in allowed_statuses


def normalize_cancel_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    normalized = " ".join(reason.strip().split())
    return normalized or None
