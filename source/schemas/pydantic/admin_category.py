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
