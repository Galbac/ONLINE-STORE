from datetime import datetime
from math import ceil

from pydantic import BaseModel, Field, model_validator


class AdminCategoryListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    include_deleted: bool = False

    @model_validator(mode="after")
    def normalize_strings(self) -> "AdminCategoryListQueryParams":
        if self.q is not None:
            self.q = self.q.strip()
            if not self.q:
                self.q = None
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    parent_id: int | None = Field(default=None, ge=1)
    image_id: int | None = Field(default=None, ge=1)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True
    meta_title: str | None = Field(default=None, max_length=255)
    meta_description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def normalize_strings(self) -> "AdminCategoryCreateRequest":
        self.name = self.name.strip()
        if self.slug is not None:
            self.slug = self.slug.strip()
            if not self.slug:
                self.slug = None
        if self.description is not None:
            self.description = self.description.strip()
            if not self.description:
                self.description = None
        if self.meta_title is not None:
            self.meta_title = self.meta_title.strip()
            if not self.meta_title:
                self.meta_title = None
        if self.meta_description is not None:
            self.meta_description = self.meta_description.strip()
            if not self.meta_description:
                self.meta_description = None
        return self


class AdminCategoryListItemResponse(BaseModel):
    id: int
    name: str
    slug: str
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int
    is_active: bool
    is_deleted: bool
    products_count: int
    created_at: datetime


class AdminCategoryDetailResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int
    is_active: bool
    created_at: datetime


class AdminCategoryListResponse(BaseModel):
    items: list[AdminCategoryListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminCategoryListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminCategoryListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )
