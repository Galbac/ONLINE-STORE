from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ProductSort = Literal["price_asc", "price_desc", "newest", "popular", "name_asc", "name_desc"]
ProductSearchSort = Literal["relevance", "price_asc", "price_desc", "newest", "popular"]
ProductType = Literal["piece", "weight"]


class ProductListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=24, ge=1, le=100)
    category_id: int | None = Field(default=None, ge=1)
    category_slug: str | None = Field(default=None, min_length=2, max_length=150)
    in_stock: bool | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    has_discount: bool | None = None
    product_type: ProductType | None = None
    sort: ProductSort | None = None

    @model_validator(mode="after")
    def validate_prices(self) -> "ProductListQueryParams":
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be less than or equal to max_price")
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class ProductDetailQueryParams(BaseModel):
    with_similar: bool = False
    with_breadcrumbs: bool = True


class ProductSearchQueryParams(BaseModel):
    q: str = Field(min_length=2, max_length=100)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=24, ge=1, le=100)
    category_id: int | None = Field(default=None, ge=1)
    in_stock: bool | None = None
    has_discount: bool | None = None
    sort: ProductSearchSort = "relevance"

    @model_validator(mode="after")
    def normalize_query(self) -> "ProductSearchQueryParams":
        self.q = self.q.strip()
        if len(self.q) < 2:
            raise ValueError("q must contain at least 2 characters")
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class ProductPopularQueryParams(BaseModel):
    limit: int = Field(default=12, ge=1, le=100)
    category_id: int | None = Field(default=None, ge=1)
    period_days: int = Field(default=30, ge=1)
    in_stock: bool = True


class ProductCategoryShortResponse(BaseModel):
    id: int
    name: str
    slug: str


class ProductShortResponse(BaseModel):
    id: int
    name: str
    slug: str
    preview_image_url: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    discount_percent: int | None = None
    unit: str
    product_type: str
    is_available: bool
    stock_display: str
    category: ProductCategoryShortResponse | None = None


class ProductImageResponse(BaseModel):
    id: int
    url: str
    sort_order: int


class ProductBreadcrumbResponse(BaseModel):
    id: int
    name: str
    slug: str


class ProductSeoResponse(BaseModel):
    meta_title: str | None = None
    meta_description: str | None = None


class ProductDetailResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    category: ProductCategoryShortResponse | None = None
    price: Decimal
    old_price: Decimal | None = None
    discount_percent: int | None = None
    unit: str
    product_type: str
    quantity_step: Decimal
    min_quantity: Decimal
    is_available: bool
    stock_quantity: Decimal
    stock_display: str
    images: list[ProductImageResponse]
    breadcrumbs: list[ProductBreadcrumbResponse] | None = None
    similar: list[ProductShortResponse] | None = None
    seo: ProductSeoResponse | None = None


class ProductListResponse(BaseModel):
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
    ) -> "ProductListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )


class ProductSearchResponse(BaseModel):
    query: str
    items: list[ProductShortResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        query: str,
        items: list[ProductShortResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "ProductSearchResponse":
        return cls(
            query=query,
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )


class ProductPopularResponse(BaseModel):
    items: list[ProductShortResponse]
    total: int
