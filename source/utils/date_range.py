from datetime import date


def validate_date_range(*, date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise ValueError("date_from must be less than or equal to date_to")
