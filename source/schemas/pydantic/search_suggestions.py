from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class SuggestionCategoryItem(BaseModel):
    id: int
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class SuggestionProductItem(BaseModel):
    id: int
    name: str
    slug: str
    article: str | None = None
    price: Decimal
    preview_image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SearchSuggestionsResponse(BaseModel):
    query: str
    categories: list[SuggestionCategoryItem]
    products: list[SuggestionProductItem]
