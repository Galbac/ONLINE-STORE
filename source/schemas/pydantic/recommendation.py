from pydantic import BaseModel, ConfigDict
from source.schemas.pydantic.product import ProductShortResponse


class ProductRecommendationResponse(BaseModel):
    product_id: int
    items: list[ProductShortResponse]

    model_config = ConfigDict(from_attributes=True)
