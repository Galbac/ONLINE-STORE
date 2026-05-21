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


class AdminPromoCodeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    discount_type: AdminPromoCodeDiscountType
    discount_value: Decimal = Field(gt=0)
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    max_discount_amount: Decimal | None = Field(default=None, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    user_usage_limit: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True
    product_ids: list[int] = Field(default_factory=list)
    category_ids: list[int] = Field(default_factory=list)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if isinstance(value, str):
            normalized_value = value.strip()
            return normalized_value or None
        return value

    @field_validator("product_ids", "category_ids")
    @classmethod
    def validate_ids(cls, value: list[int]) -> list[int]:
        unique_ids = list(dict.fromkeys(value))
        if any(item_id <= 0 for item_id in unique_ids):
            raise ValueError("ids must be positive")
        return unique_ids

    @model_validator(mode="after")
    def validate_promo_code(self) -> "AdminPromoCodeCreateRequest":
        if self.discount_type == "percent" and not Decimal("1") <= self.discount_value <= Decimal("100"):
            raise ValueError("percent discount_value must be between 1 and 100")
        if self.starts_at is not None and self.ends_at is not None and self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be less than ends_at")
        return self


class AdminPromoCodeUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    discount_type: AdminPromoCodeDiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0)
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    max_discount_amount: Decimal | None = Field(default=None, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    user_usage_limit: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    product_ids: list[int] | None = None
    category_ids: list[int] | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if isinstance(value, str):
            normalized_value = value.strip()
            return normalized_value or None
        return value

    @field_validator("product_ids", "category_ids")
    @classmethod
    def validate_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        unique_ids = list(dict.fromkeys(value))
        if any(item_id <= 0 for item_id in unique_ids):
            raise ValueError("ids must be positive")
        return unique_ids

    @model_validator(mode="after")
    def validate_promo_code(self) -> "AdminPromoCodeUpdateRequest":
        if self.discount_type == "percent" and self.discount_value is not None:
            if not Decimal("1") <= self.discount_value <= Decimal("100"):
                raise ValueError("percent discount_value must be between 1 and 100")
        if self.starts_at is not None and self.ends_at is not None and self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be less than ends_at")
        return self


class AdminPromoCodeProductResponse(BaseModel):
    id: int
    name: str
    price: Decimal


class AdminPromoCodeCategoryResponse(BaseModel):
    id: int
    name: str


class AdminPromoCodeDetailResponse(BaseModel):
    id: int
    code: str
    name: str | None = None
    description: str | None = None
    discount_type: str
    discount_value: Decimal
    min_order_amount: Decimal | None = None
    max_discount_amount: Decimal | None = None
    usage_limit: int | None = None
    usage_count: int = 0
    user_usage_limit: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool
    updated_at: datetime | None = None
    products: list[AdminPromoCodeProductResponse] = Field(default_factory=list)
    categories: list[AdminPromoCodeCategoryResponse] = Field(default_factory=list)


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
