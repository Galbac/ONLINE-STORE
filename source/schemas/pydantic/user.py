from datetime import date, datetime

from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator, model_validator

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


class AdminUserListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    is_blocked: bool | None = None
    is_deleted: bool | None = None
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("q", mode="before")
    @classmethod
    def normalize_q(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @model_validator(mode="after")
    def validate_dates(self) -> "AdminUserListQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminUserListItemResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    is_active: bool
    is_blocked: bool
    orders_count: int
    total_spent: Decimal
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminUserListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminUserListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total else 0,
        )


class AdminUserAddressResponse(BaseModel):
    id: int
    title: str | None = None
    city: str
    street: str
    house: str
    building: str | None = None
    apartment: str | None = None
    entrance: str | None = None
    floor: str | None = None
    intercom: str | None = None
    comment: str | None = None
    is_default: bool
    created_at: datetime


class AdminUserOrderShortResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_method: str | None = None
    payment_status: str | None = None
    delivery_type: str | None = None
    final_price: Decimal
    items_count: int = 0
    created_at: datetime


class AdminUserDetailResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    is_active: bool
    is_blocked: bool
    is_deleted: bool
    orders_count: int
    total_spent: Decimal
    addresses: list[AdminUserAddressResponse]
    recent_orders: list[AdminUserOrderShortResponse]
    created_at: datetime
