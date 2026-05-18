from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from source.schemas.pydantic.cart import CartResponse


class PromoCodeCheckRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    cart_total: Decimal | None = Field(default=None, ge=0)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class PromoCodeCheckResponse(BaseModel):
    valid: bool
    code: str
    discount_type: str | None = None
    discount_value: Decimal | None = None
    discount_amount: Decimal | None = None
    min_order_amount: Decimal | None = None
    amount_left: Decimal | None = None
    message: str


class PromoCodeApplyRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class PromoCodeApplyResponse(BaseModel):
    message: str
    cart: CartResponse
