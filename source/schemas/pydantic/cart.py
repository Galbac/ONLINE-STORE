from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


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


class CartSummaryResponse(BaseModel):
    items_count: int
    total_quantity: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    promo_discount_amount: Decimal
    delivery_price: Decimal | None = None
    final_price: Decimal
    has_warnings: bool
    warnings_count: int
    promo_code: str | None = None


class CartItemCreateRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)


class CartItemUpdateRequest(BaseModel):
    quantity: Decimal = Field(gt=0)


class ApplyPromoCodeRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class MessageCartResponse(BaseModel):
    message: str
    cart: CartResponse
