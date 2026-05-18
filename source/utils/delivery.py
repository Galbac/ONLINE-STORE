from datetime import date, datetime
from decimal import Decimal

from source.config.settings import settings


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


def validate_future_date(value: date) -> date:
    if value < datetime.now(settings.tz).date():
        raise ValueError("date не должна быть в прошлом")
    return value


def get_weekday(value: date) -> int:
    return value.weekday()
