from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator, model_validator

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
    payment_method: str | None = None
    payment_status: str | None = None
    delivery_type: str | None = None
    items_count: int = 0
    final_price: Decimal
    created_at: datetime


class OrderMyListQueryParams(BaseModel):
    status: str | None = Field(default=None, max_length=50)
    payment_status: str | None = Field(default=None, max_length=50)
    delivery_type: str | None = Field(default=None, pattern="^(delivery|pickup)$")
    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("status", "payment_status", "delivery_type", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = value.strip()
        return normalized_value or None

    @model_validator(mode="after")
    def validate_dates(self) -> "OrderMyListQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class OrderMyListResponse(BaseModel):
    items: list[OrderShortResponse]
    total: int
    page: int
    limit: int
    pages: int


class OrderCreateResponse(BaseModel):
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
