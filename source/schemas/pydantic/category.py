from pydantic import BaseModel, Field


class CategoryListQueryParams(BaseModel):
    parent_id: int | None = Field(default=None, ge=1)
    only_root: bool = False
    include_empty: bool = False
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class CategoryTreeQueryParams(BaseModel):
    include_empty: bool = False
    max_depth: int = Field(default=3, ge=1, le=10)
    root_id: int | None = Field(default=None, ge=1)
    with_products_count: bool = True


class CategoryShortResponse(BaseModel):
    id: int
    name: str
    slug: str
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int
    products_count: int


class CategoryListResponse(BaseModel):
    items: list[CategoryShortResponse]
    total: int
    limit: int
    offset: int


class CategoryTreeItemResponse(BaseModel):
    id: int
    name: str
    slug: str
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int
    products_count: int | None = None
    children: list["CategoryTreeItemResponse"] = Field(default_factory=list)


class CategoryTreeResponse(BaseModel):
    items: list[CategoryTreeItemResponse]
