import re
from pydantic import ValidationError


def format_validation_error_message(msg: str) -> str:
    """Локализует сообщения валидации Pydantic на понятный русский язык."""
    if not msg:
        return "Неверные входные данные"

    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]

    msg_lower = msg.lower()

    # Email
    if "value is not a valid email address" in msg_lower or "the part after the @-sign is not valid" in msg_lower:
        if "top-level domain" in msg_lower or "domain" in msg_lower:
            return "Некорректный адрес электронной почты: неверный домен (например, .ru или .com)"
        if "@-sign" in msg_lower or "at-sign" in msg_lower:
            return "Некорректный адрес электронной почты: отсутствует или некорректен символ @"
        return "Некорректный адрес электронной почты"

    # Required fields
    if "field required" in msg_lower:
        return "Поле обязательно для заполнения"

    # Type errors
    if "input should be a valid integer" in msg_lower:
        return "Значение должно быть целым числом"
    if "input should be a valid number" in msg_lower or "input should be a valid decimal" in msg_lower:
        return "Значение должно быть числом"
    if "input should be a valid boolean" in msg_lower:
        return "Значение должно быть логическим (да/нет)"
    if "input should be a valid string" in msg_lower:
        return "Значение должно быть строкой"
    if "input should be a valid url" in msg_lower or "url" in msg_lower and "not valid" in msg_lower:
        return "Некорректный URL-адрес"

    # Extra inputs
    if "extra inputs are not permitted" in msg_lower:
        return "Переданы непредусмотренные поля"

    # Length constraints
    at_least_match = re.search(r"string should have at least (\d+) characters?", msg_lower)
    if at_least_match:
        return f"Минимальная длина: {at_least_match.group(1)} симв."

    at_most_match = re.search(r"string should have at most (\d+) characters?", msg_lower)
    if at_most_match:
        return f"Максимальная длина: {at_most_match.group(1)} симв."

    greater_match = re.search(r"input should be greater than (?:or equal to )?([-\d.]+)", msg_lower)
    if greater_match:
        return f"Значение должно быть больше {greater_match.group(1)}"

    less_match = re.search(r"input should be less than (?:or equal to )?([-\d.]+)", msg_lower)
    if less_match:
        return f"Значение должно быть меньше {less_match.group(1)}"

    return msg


def format_pydantic_validation_error(error: ValidationError) -> str:
    """Извлекает первую ошибку из ValidationError и возвращает локализованное сообщение."""
    if not error.errors():
        return "Неверные входные данные"
    first = error.errors()[0]
    msg = first.get("msg", "")
    return format_validation_error_message(str(msg))
