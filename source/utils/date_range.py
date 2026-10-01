from datetime import date


def validate_date_range(*, date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise ValueError("Начальная дата (date_from) должна быть меньше или равна конечной дате (date_to)")
