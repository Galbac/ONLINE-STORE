from math import ceil

from pydantic import BaseModel, Field

from source.schemas.pydantic.product import ProductShortResponse


class FavoritesQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=24, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class FavoriteProductResponse(ProductShortResponse):
    pass


class FavoritesResponse(BaseModel):
    items: list[FavoriteProductResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[FavoriteProductResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "FavoritesResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )
