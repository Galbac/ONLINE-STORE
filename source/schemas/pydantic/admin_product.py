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


class AdminProductCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255)
    description: str | None = None
    category_id: int = Field(ge=1)
    price: Decimal = Field(gt=0)
    old_price: Decimal | None = Field(default=None, gt=0)
    unit: str = Field(min_length=1, max_length=20)
    product_type: ProductType
    quantity_step: Decimal = Field(gt=0)
    min_quantity: Decimal = Field(gt=0)
    stock_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    low_stock_threshold: Decimal = Field(gt=0)
    is_active: bool = True
    is_available: bool = True
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    barcode: str | None = Field(default=None, min_length=1, max_length=100)
    meta_title: str | None = Field(default=None, max_length=255)
    meta_description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_product_quantities(self) -> "AdminProductCreateRequest":
        self.name = self.name.strip()
        self.slug = self.slug.strip()
        self.unit = self.unit.strip()
        self.sku = self.sku.strip() if self.sku is not None else None
        self.barcode = self.barcode.strip() if self.barcode is not None else None
        if self.product_type == "piece":
            if self.min_quantity < 1:
                raise ValueError("min_quantity must be greater than or equal to 1 for piece products")
            if self.quantity_step != Decimal("1"):
                raise ValueError("quantity_step must be 1 for piece products")
        if self.product_type == "weight" and self.quantity_step not in {
            Decimal("0.1"),
            Decimal("0.5"),
            Decimal("1"),
        }:
            raise ValueError("quantity_step must be one of 0.1, 0.5, 1 for weight products")
        return self


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


class AdminProductDetailResponse(BaseModel):
    id: int
    name: str
    slug: str
    category_id: int
    price: Decimal
    unit: str
    product_type: str
    stock_quantity: Decimal
    is_active: bool
    is_available: bool


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
