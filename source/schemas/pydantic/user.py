from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from source.db.models.choises.enum import UserRole
from source.utils.user_profile import normalize_email, validate_phone


class UserMeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, min_length=5, max_length=32)
    email: EmailStr | None = None

    @field_validator("name", "phone", mode="before")
    @classmethod
    def strip_string(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_phone(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return value
        return normalize_email(value)


class UserMeDeleteRequest(BaseModel):
    password: str = Field(min_length=1)
    confirm: bool


class UserMeResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    role: UserRole
    is_active: bool
    is_verified: bool = False
    created_at: datetime
    updated_at: datetime
