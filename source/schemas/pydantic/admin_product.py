from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from source.schemas.pydantic.product import ProductType


AdminProductSort = Literal["newest", "name_asc", "price_asc", "stock_asc"]


class AdminProductListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    is_available: bool | None = None
    in_stock: bool | None = None
    low_stock: bool | None = None
    product_type: ProductType | None = None
    sync_status: str | None = Field(default=None, min_length=1, max_length=50)
    sort: AdminProductSort = "newest"

    @model_validator(mode="after")
    def normalize_strings(self) -> "AdminProductListQueryParams":
        if self.q is not None:
            self.q = self.q.strip()
            if not self.q:
                self.q = None
        if self.sync_status is not None:
            self.sync_status = self.sync_status.strip()
            if not self.sync_status:
                self.sync_status = None
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminProductCategoryResponse(BaseModel):
    id: int
    name: str


class AdminProductListItemResponse(BaseModel):
    id: int
    name: str
    slug: str
    sku: str | None = None
    barcode: str | None = None
    category: AdminProductCategoryResponse | None = None
    price: Decimal
    unit: str
    product_type: str
    stock_quantity: Decimal
    low_stock_threshold: Decimal
    is_active: bool
    is_available: bool
    sync_status: str | None = None
    external_1c_id: str | None = None


class AdminProductListResponse(BaseModel):
    items: list[AdminProductListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminProductListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminProductListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )
