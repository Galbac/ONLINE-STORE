from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from source.db.models.choises.enum import UserRole


class ProfileUserResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    role: UserRole
    is_active: bool
    is_verified: bool = False


class ProfileStatsResponse(BaseModel):
    orders_count: int
    addresses_count: int


class ProfileAddressShortResponse(BaseModel):
    id: int
    city: str
    street: str
    house: str
    apartment: str | None = None


class AddressListQueryParams(BaseModel):
    include_deleted: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AddressResponse(BaseModel):
    id: int
    title: str | None = None
    city: str
    street: str
    house: str
    building: str | None = None
    apartment: str | None = None
    entrance: str | None = None
    floor: str | None = None
    intercom: str | None = None
    comment: str | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class AddressCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    street: str = Field(min_length=1, max_length=150)
    house: str = Field(min_length=1, max_length=50)
    building: str | None = Field(default=None, max_length=50)
    apartment: str | None = Field(default=None, max_length=50)
    entrance: str | None = Field(default=None, max_length=50)
    floor: str | None = Field(default=None, max_length=50)
    intercom: str | None = Field(default=None, max_length=50)
    comment: str | None = Field(default=None, max_length=500)
    is_default: bool = False

    @field_validator(
        "title",
        "city",
        "street",
        "house",
        "building",
        "apartment",
        "entrance",
        "floor",
        "intercom",
        "comment",
        mode="before",
    )
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class AddressUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    street: str | None = Field(default=None, min_length=1, max_length=150)
    house: str | None = Field(default=None, min_length=1, max_length=50)
    building: str | None = Field(default=None, max_length=50)
    apartment: str | None = Field(default=None, max_length=50)
    entrance: str | None = Field(default=None, max_length=50)
    floor: str | None = Field(default=None, max_length=50)
    intercom: str | None = Field(default=None, max_length=50)
    comment: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None

    @field_validator(
        "title",
        "city",
        "street",
        "house",
        "building",
        "apartment",
        "entrance",
        "floor",
        "intercom",
        "comment",
        mode="before",
    )
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class AddressListResponse(BaseModel):
    items: list[AddressResponse]
    total: int
    limit: int
    offset: int


class ProfileOrderShortResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_method: str | None = None
    payment_status: str | None = None
    delivery_type: str | None = None
    final_price: Decimal
    items_count: int = 0
    created_at: datetime


class ProfileOrderListQueryParams(BaseModel):
    status: str | None = Field(default=None, max_length=50)
    payment_status: str | None = Field(default=None, max_length=50)
    delivery_type: str | None = Field(default=None, pattern="^(delivery|pickup)$")
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("status", "payment_status", "delivery_type", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = value.strip()
        return normalized_value or None

    @model_validator(mode="after")
    def validate_dates(self) -> "ProfileOrderListQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self


class ProfileOrderListResponse(BaseModel):
    items: list[ProfileOrderShortResponse]
    total: int
    limit: int
    offset: int


class RepeatOrderRequest(BaseModel):
    replace_cart: bool = False


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    name: str
    quantity: Decimal
    unit: str
    price: Decimal
    total_price: Decimal


class CartResponse(BaseModel):
    id: int
    items: list[CartItemResponse]
    total_price: Decimal
    discount_amount: Decimal = Decimal("0")
    final_price: Decimal


class RepeatOrderWarningResponse(BaseModel):
    product_id: int
    product_name: str
    reason: str


class RepeatOrderResponse(BaseModel):
    message: str
    cart: CartResponse
    warnings: list[RepeatOrderWarningResponse]


class ProfileSummaryResponse(BaseModel):
    user: ProfileUserResponse
    stats: ProfileStatsResponse
    default_address: ProfileAddressShortResponse | None = None
    active_order: ProfileOrderShortResponse | None = None
    recent_orders: list[ProfileOrderShortResponse]
