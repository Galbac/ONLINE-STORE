from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from source.utils.order import normalize_phone


class OrderCreateRequest(BaseModel):
    delivery_type: str = Field(pattern="^(delivery|pickup)$")
    payment_method: str = Field(pattern="^(online|on_delivery)$")
    address_id: int | None = Field(default=None, gt=0)
    pickup_point_id: int | None = Field(default=None, gt=0)
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=5, max_length=32)
    customer_email: EmailStr | None = None
    delivery_date: date | None = None
    delivery_time_slot_id: int | None = Field(default=None, gt=0)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("customer_name", "comment", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        if value is None:
            return value
        return " ".join(value.strip().split())

    @field_validator("customer_phone", mode="before")
    @classmethod
    def normalize_customer_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @model_validator(mode="after")
    def validate_delivery_target(self) -> "OrderCreateRequest":
        if self.delivery_type == "delivery" and self.address_id is None:
            raise ValueError("address_id обязателен для доставки")
        if self.delivery_type == "pickup" and self.pickup_point_id is None:
            raise ValueError("pickup_point_id обязателен для самовывоза")
        return self


class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    product_slug: str
    price: Decimal
    old_price: Decimal | None = None
    quantity: Decimal
    unit: str
    product_type: str
    discount_amount: Decimal
    total_price: Decimal
    final_price: Decimal


class OrderUnavailableItemResponse(BaseModel):
    product_id: int
    name: str
    reason: str
    requested_quantity: Decimal
    available_quantity: Decimal


class OrderShortResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_method: str
    payment_status: str
    delivery_type: str
    subtotal: Decimal
    discount_amount: Decimal
    promo_discount_amount: Decimal
    delivery_price: Decimal
    final_price: Decimal
    payment_url: str | None = None
    created_at: datetime


class OrderCreateResponse(OrderShortResponse):
    pass
