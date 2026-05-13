import re

from pydantic import EmailStr, TypeAdapter


def normalize_phone(phone: str) -> str:
    return phone.strip()


def validate_phone(phone: str) -> str:
    normalized_phone = normalize_phone(phone)
    if re.fullmatch(r"\+?\d{5,15}", normalized_phone) is None:
        raise ValueError("Неверный формат телефона")
    return normalized_phone


def normalize_email(email: str | EmailStr) -> str:
    return str(email).strip().lower()


def validate_email(email: str) -> str:
    normalized_email = normalize_email(email)
    TypeAdapter(EmailStr).validate_python(normalized_email)
    return normalized_email
