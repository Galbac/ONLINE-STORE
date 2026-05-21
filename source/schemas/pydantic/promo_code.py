from datetime import date, datetime
from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from source.schemas.pydantic.cart import CartResponse


AdminPromoCodeDiscountType = Literal["percent", "fixed_amount"]


class AdminPromoCodeListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    discount_type: AdminPromoCodeDiscountType | None = None
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
    def validate_dates(self) -> "AdminPromoCodeListQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminPromoCodeListItemResponse(BaseModel):
    id: int
    code: str
    name: str | None = None
    discount_type: str
    discount_value: Decimal
    min_order_amount: Decimal | None = None
    usage_limit: int | None = None
    usage_count: int
    user_usage_limit: int | None = None
    is_active: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AdminPromoCodeListResponse(BaseModel):
    items: list[AdminPromoCodeListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminPromoCodeListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminPromoCodeListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )


class PromoCodeCheckRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    cart_total: Decimal | None = Field(default=None, ge=0)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class PromoCodeCheckResponse(BaseModel):
    valid: bool
    code: str
    discount_type: str | None = None
    discount_value: Decimal | None = None
    discount_amount: Decimal | None = None
    min_order_amount: Decimal | None = None
    amount_left: Decimal | None = None
    message: str


class PromoCodeApplyRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class PromoCodeApplyResponse(BaseModel):
    message: str
    cart: CartResponse
