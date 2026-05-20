from datetime import date, datetime
from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from source.schemas.pydantic.product import ProductShortResponse


DiscountType = Literal["product", "category", "cart"]
DiscountValueType = Literal["percent", "fixed_price", "fixed_amount"]
DiscountProductsSort = Literal["discount_desc", "price_asc", "price_desc", "newest"]


class ActiveDiscountsQueryParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    type: DiscountType | None = None
    only_with_products: bool = True


class DiscountShortResponse(BaseModel):
    id: int
    name: str
    type: str
    discount_type: str
    discount_value: Decimal
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool


class ActiveDiscountsResponse(BaseModel):
    items: list[DiscountShortResponse]
    total: int
    limit: int
    offset: int


class DiscountProductsQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=24, ge=1, le=100)
    category_id: int | None = Field(default=None, ge=1)
    in_stock: bool = True
    sort: DiscountProductsSort = "discount_desc"

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class DiscountProductsResponse(BaseModel):
    items: list[ProductShortResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[ProductShortResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "DiscountProductsResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )


class AdminDiscountListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    type: DiscountType | None = None
    discount_type: DiscountValueType | None = None
    is_active: bool | None = None
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
    def validate_dates(self) -> "AdminDiscountListQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminDiscountListItemResponse(BaseModel):
    id: int
    name: str
    type: str
    discount_type: str
    discount_value: Decimal
    is_active: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime


class AdminDiscountListResponse(BaseModel):
    items: list[AdminDiscountListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminDiscountListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminDiscountListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total else 0,
        )
