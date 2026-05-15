from decimal import Decimal

from pydantic import BaseModel
from pydantic import Field


class CartWarningResponse(BaseModel):
    product_id: int
    message: str


class CartPromoCodeResponse(BaseModel):
    code: str
    discount_amount: Decimal


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    name: str
    slug: str | None = None
    preview_image_url: str | None = None
    quantity: Decimal
    unit: str
    product_type: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    discount_amount: Decimal = Decimal("0")
    total_price: Decimal
    final_price: Decimal
    is_available: bool
    stock_quantity: Decimal
    stock_warning: str | None = None


class CartResponse(BaseModel):
    id: int
    items: list[CartItemResponse]
    promo_code: CartPromoCodeResponse | None = None
    items_count: int
    total_quantity: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    promo_discount_amount: Decimal
    delivery_price: Decimal | None = None
    final_price: Decimal
    warnings: list[CartWarningResponse]


class CartItemCreateRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)


class MessageCartResponse(BaseModel):
    message: str
    cart: CartResponse
