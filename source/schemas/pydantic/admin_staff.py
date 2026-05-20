from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

from source.db.models.choises.enum import UserRole
from source.utils.user_profile import normalize_email, validate_phone


class AdminStaffListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None
    is_blocked: bool | None = None

    @field_validator("q", mode="before")
    @classmethod
    def normalize_q(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminStaffListItemResponse(BaseModel):
    id: int
    name: str
    email: EmailStr | None
    phone: str
    role: UserRole
    is_active: bool
    is_blocked: bool
    created_at: datetime


class AdminStaffListResponse(BaseModel):
    items: list[AdminStaffListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminStaffListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminStaffListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total else 0,
        )


class AdminStaffCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    email: EmailStr | None = None
    phone: str = Field(min_length=5, max_length=32)
    password: str = Field(min_length=8)
    role: UserRole
    is_active: bool = True

    @field_validator("name", "phone", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return " ".join(value.strip().split())

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return value
        return str(value).lower()

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        has_upper = any(char.isupper() for char in value)
        has_lower = any(char.islower() for char in value)
        has_digit = any(char.isdigit() for char in value)
        if not (has_upper and has_lower and has_digit):
            raise ValueError("Пароль слишком слабый")
        return value


class AdminStaffUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=5, max_length=32)
    is_active: bool | None = None

    @field_validator("name", "phone", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return " ".join(value.strip().split())
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


class AdminStaffDetailResponse(BaseModel):
    id: int
    name: str
    email: EmailStr | None
    phone: str
    role: UserRole
    permissions: list[str] = Field(default_factory=list)
    is_active: bool
    is_blocked: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
