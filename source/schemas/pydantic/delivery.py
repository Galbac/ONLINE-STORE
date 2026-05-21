from datetime import date, datetime
from decimal import Decimal
from math import ceil

from pydantic import BaseModel, Field, field_validator, model_validator

from source.utils.delivery import normalize_address_part


class DeliveryOptionItemResponse(BaseModel):
    enabled: bool
    title: str
    description: str | None = None
    min_order_amount: Decimal | None = None
    base_price: Decimal | None = None
    free_from_amount: Decimal | None = None
    has_time_slots: bool | None = None
    price: Decimal | None = None
    has_pickup_points: bool | None = None


class DeliveryOptionsResponse(BaseModel):
    delivery: DeliveryOptionItemResponse
    pickup: DeliveryOptionItemResponse


class AdminDeliverySettingsResponse(BaseModel):
    delivery_enabled: bool
    pickup_enabled: bool
    min_order_amount: Decimal
    base_delivery_price: Decimal
    free_delivery_from: Decimal | None = None
    time_slots_enabled: bool
    delivery_comment: str | None = None
    pickup_comment: str | None = None
    default_city: str | None = None
    currency: str
    updated_at: datetime | None = None


class AdminDeliverySettingsUpdateRequest(BaseModel):
    delivery_enabled: bool | None = None
    pickup_enabled: bool | None = None
    min_order_amount: Decimal | None = None
    base_delivery_price: Decimal | None = None
    free_delivery_from: Decimal | None = None
    time_slots_enabled: bool | None = None
    delivery_comment: str | None = Field(default=None, max_length=1000)
    pickup_comment: str | None = Field(default=None, max_length=1000)
    default_city: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("delivery_comment", "pickup_comment", "default_city", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if isinstance(value, str):
            normalized_value = " ".join(value.strip().split())
            return normalized_value or None
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if isinstance(value, str):
            return value.strip().upper()
        return value


class AdminDeliveryZoneListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    include_deleted: bool = False

    @model_validator(mode="after")
    def normalize_strings(self) -> "AdminDeliveryZoneListQueryParams":
        for field in ("q", "city"):
            value = getattr(self, field)
            if value is not None:
                value = value.strip()
                setattr(self, field, value or None)
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminDeliveryZoneResponse(BaseModel):
    id: int
    name: str
    city: str
    description: str | None = None
    delivery_price: Decimal | None = None
    free_delivery_from: Decimal | None = None
    min_order_amount: Decimal | None = None
    is_active: bool
    is_deleted: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class AdminDeliveryZoneListResponse(BaseModel):
    items: list[AdminDeliveryZoneResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminDeliveryZoneResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminDeliveryZoneListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=ceil(total / limit) if total else 0,
        )


class DeliveryCalculateRequest(BaseModel):
    city: str | None = Field(default=None, min_length=1, max_length=100)
    street: str | None = Field(default=None, min_length=1, max_length=150)
    house: str | None = Field(default=None, min_length=1, max_length=50)
    apartment: str | None = Field(default=None, max_length=50)
    order_amount: Decimal = Field(gt=0)
    address_id: int | None = Field(default=None, gt=0)

    @field_validator("city", "street", "house", "apartment", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        return normalize_address_part(value)

    @model_validator(mode="after")
    def validate_address_fields(self) -> "DeliveryCalculateRequest":
        if self.address_id is None and (self.city is None or self.street is None or self.house is None):
            raise ValueError("city, street и house обязательны, если address_id не передан")
        return self


class DeliveryZoneShortResponse(BaseModel):
    id: int
    name: str


class DeliveryCalculateResponse(BaseModel):
    available: bool
    delivery_price: Decimal | None = None
    free_delivery_from: Decimal | None = None
    amount_left_for_free_delivery: Decimal | None = None
    min_order_amount: Decimal | None = None
    zone: DeliveryZoneShortResponse | None = None
    message: str


class PickupPointListQueryParams(BaseModel):
    city: str | None = Field(default=None, max_length=100)
    only_active: bool = True
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("city", mode="before")
    @classmethod
    def normalize_city(cls, value: str | None) -> str | None:
        return normalize_address_part(value)


class PickupPointResponse(BaseModel):
    id: int
    name: str
    city: str
    address: str
    working_hours: str | None = None
    phone: str | None = None
    is_active: bool
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class PickupPointDetailResponse(PickupPointResponse):
    description: str | None = None


class PickupPointListResponse(BaseModel):
    items: list[PickupPointResponse]
    total: int
    limit: int
    offset: int


class DeliveryTimeSlotsQueryParams(BaseModel):
    date: date
    delivery_type: str = Field(pattern="^(delivery|pickup)$")
    pickup_point_id: int | None = Field(default=None, gt=0)
    address_id: int | None = Field(default=None, gt=0)
    city: str | None = Field(default=None, max_length=100)

    @field_validator("city", mode="before")
    @classmethod
    def normalize_slot_city(cls, value: str | None) -> str | None:
        return normalize_address_part(value)


class DeliveryTimeSlotResponse(BaseModel):
    id: int
    start_time: str
    end_time: str
    label: str
    available: bool
    orders_limit: int | None = None
    orders_count: int | None = None
    reason: str | None = None


class DeliveryTimeSlotsResponse(BaseModel):
    date: date
    delivery_type: str
    items: list[DeliveryTimeSlotResponse]
