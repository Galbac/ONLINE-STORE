from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, Field

from source.schemas.pydantic.product import ProductShortResponse


DiscountType = Literal["product", "category", "cart"]
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
