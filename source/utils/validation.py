import re
from pydantic import ValidationError

FIELD_NAMES_RU: dict[str, str] = {
    "order_amount": "«Сумма заказа» (order_amount)",
    "cart_total": "«Сумма корзины» (cart_total)",
    "address_id": "«ID адреса» (address_id)",
    "pickup_point_id": "«ID точки самовывоза» (pickup_point_id)",
    "city": "«Город» (city)",
    "street": "«Улица» (street)",
    "house": "«Номер дома» (house)",
    "apartment": "«Квартира» (apartment)",
    "delivery_type": "«Тип доставки» (delivery_type)",
    "phone": "«Номер телефона» (phone)",
    "email": "«Электронная почта» (email)",
    "password": "«Пароль» (password)",
    "code": "«Код подтверждения» (code)",
    "full_name": "«ФИО» (full_name)",
    "first_name": "«Имя» (first_name)",
    "last_name": "«Фамилия» (last_name)",
    "shop_name": "«Название магазина» (shop_name)",
}


def format_validation_error_message(msg: str) -> str:
    """Локализует сообщения валидации Pydantic на понятный русский язык."""
    if not msg:
        return "Неверные входные данные"

    if msg.startswith("Value error, "):
        return msg[len("Value error, "):]

    msg_lower = msg.lower()

    # Email
    if "value is not a valid email address" in msg_lower or "the part after the @-sign is not valid" in msg_lower:
        if "top-level domain" in msg_lower or "domain" in msg_lower:
            return "неверный домен (например, .ru или .com)"
        if "@-sign" in msg_lower or "at-sign" in msg_lower:
            return "отсутствует или некорректен символ @"
        return "некорректный адрес электронной почты"

    # Required fields
    if "field required" in msg_lower:
        return "обязательно для заполнения"

    # Type errors
    if "input should be a valid integer" in msg_lower:
        return "должно быть целым числом"
    if "input should be a valid number" in msg_lower or "input should be a valid decimal" in msg_lower:
        return "должно быть числом"
    if "input should be a valid boolean" in msg_lower:
        return "должно быть логическим (да/нет)"
    if "input should be a valid string" in msg_lower:
        return "должно быть строкой"
    if "input should be a valid url" in msg_lower or "url" in msg_lower and "not valid" in msg_lower:
        return "некорректный URL-адрес"

    # Extra inputs
    if "extra inputs are not permitted" in msg_lower:
        return "переданы непредусмотренные поля"

    # Length constraints
    at_least_match = re.search(r"string should have at least (\d+) characters?", msg_lower)
    if at_least_match:
        return f"минимальная длина: {at_least_match.group(1)} симв."

    at_most_match = re.search(r"string should have at most (\d+) characters?", msg_lower)
    if at_most_match:
        return f"максимальная длина: {at_most_match.group(1)} симв."

    greater_match = re.search(r"input should be greater than (?:or equal to )?([-\d.]+)", msg_lower)
    if greater_match:
        return f"должно быть больше {greater_match.group(1)}"

    less_match = re.search(r"input should be less than (?:or equal to )?([-\d.]+)", msg_lower)
    if less_match:
        return f"должно быть меньше {less_match.group(1)}"

    return msg


def format_pydantic_validation_error(error: ValidationError) -> str:
    """Извлекает первую ошибку из ValidationError и возвращает понятное локализованное сообщение с указанием поля."""
    if not error.errors():
        return "Неверные входные данные"
    first = error.errors()[0]
    raw_msg = first.get("msg", "")

    # Пользовательские ошибки из валидаторов Pydantic уже содержат целевой текст
    if raw_msg.startswith("Value error, "):
        return raw_msg[len("Value error, "):]

    formatted = format_validation_error_message(raw_msg)
    loc = [str(x) for x in first.get("loc", ()) if x != "__root__"]
    if loc:
        field_key = loc[-1]
        field_title = FIELD_NAMES_RU.get(field_key, f"«{field_key}»")
        if "обязательно для заполнения" in formatted:
            return f"Поле {field_title} обязательно для заполнения"
        return f"Поле {field_title}: {formatted}"

    return formatted
