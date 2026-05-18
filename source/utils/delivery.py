from decimal import Decimal


def normalize_address(
    *,
    city: str,
    street: str,
    house: str,
    apartment: str | None = None,
) -> dict[str, str | None]:
    return {
        "city": normalize_address_part(city),
        "street": normalize_address_part(street),
        "house": normalize_address_part(house),
        "apartment": normalize_address_part(apartment),
    }


def normalize_address_part(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = " ".join(value.strip().split())
    return normalized_value or None


def normalize_amount(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))
