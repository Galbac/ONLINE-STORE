from decimal import Decimal


def calculate_discount_percent(*, price: Decimal, old_price: Decimal | None) -> int | None:
    if old_price is None or old_price <= price or old_price <= 0:
        return None
    return int(((old_price - price) / old_price * Decimal("100")).quantize(Decimal("1")))
