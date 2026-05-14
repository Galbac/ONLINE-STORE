import re


SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{2,200}$")


def normalize_slug(slug: str) -> str:
    return slug.strip().lower()


def validate_slug(slug: str) -> bool:
    return bool(SLUG_PATTERN.fullmatch(slug))
