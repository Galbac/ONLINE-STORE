from datetime import date, datetime
from decimal import Decimal
from typing import Literal

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
    id: int | None = None
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

    @classmethod
    def build(cls, *, items: list[OrderShortResponse], total: int, page: int, limit: int) -> "OrderMyListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total else 0,
        )


class AdminOrderListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, max_length=50)
    payment_status: str | None = Field(default=None, max_length=50)
    payment_method: Literal["online", "on_delivery"] | None = None
    delivery_type: Literal["delivery", "pickup"] | None = None
    sync_status: str | None = Field(default=None, max_length=50)
    date_from: date | None = None
    date_to: date | None = None
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)

    @field_validator(
        "q",
        "status",
        "payment_status",
        "payment_method",
        "delivery_type",
        "sync_status",
        mode="before",
    )
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @model_validator(mode="after")
    def validate_ranges(self) -> "AdminOrderListQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            raise ValueError("min_amount must be less than or equal to max_amount")
        return self

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminOrderListItemResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_method: str | None = None
    payment_status: str | None = None
    delivery_type: str
    customer_name: str
    customer_phone: str
    final_price: Decimal
    sync_status: str
    created_at: datetime


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminOrderListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminOrderListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total else 0,
        )


class AdminOrderCustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: str | None = None


class AdminOrderAddressResponse(BaseModel):
    city: str
    street: str
    house: str
    apartment: str | None = None


class AdminOrderPickupPointResponse(BaseModel):
    id: int
    name: str
    city: str
    address: str


class AdminOrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: Decimal
    unit: str
    price: Decimal
    final_price: Decimal


class AdminOrderPaymentResponse(BaseModel):
    id: int
    amount: Decimal
    currency: str
    status: str
    provider: str | None = None
    provider_payment_id: str | None = None
    paid_at: datetime | None = None
    cancelled_at: datetime | None = None
    refund_status: str | None = None


class AdminOrderStatusHistoryItemResponse(BaseModel):
    status: str
    created_at: datetime
    comment: str | None = None


class AdminOrderDetailResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_method: str | None = None
    payment_status: str | None = None
    delivery_type: str
    customer: AdminOrderCustomerResponse
    address: AdminOrderAddressResponse | None = None
    pickup_point: AdminOrderPickupPointResponse | None = None
    items: list[AdminOrderItemResponse]
    payment: AdminOrderPaymentResponse | None = None
    status_history: list[AdminOrderStatusHistoryItemResponse] = Field(default_factory=list)
    comment: str | None = None
    cancel_reason: str | None = None
    subtotal: Decimal
    discount_amount: Decimal
    promo_discount_amount: Decimal
    delivery_price: Decimal
    final_price: Decimal
    sync_status: str
    external_1c_id: str | None = None
    created_at: datetime


class AdminOrderPrintItemResponse(BaseModel):
    name: str
    quantity: Decimal
    unit: str
    comment: str | None = None


class AdminOrderPrintResponse(BaseModel):
    order_number: str
    created_at: datetime
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    delivery_type: str
    address: str | None = None
    items: list[AdminOrderPrintItemResponse]
    comment: str | None = None
    final_price: Decimal


class AdminOrderStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=50)
    comment: str | None = Field(default=None, max_length=500)
    notify_customer: bool = False

    @field_validator("status", "comment", mode="before")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class AdminOrderStatusResponse(BaseModel):
    id: int
    order_number: str
    status: str
    updated_at: datetime


class AdminOrderUpdateRequest(BaseModel):
    customer_name: str | None = Field(default=None, min_length=1, max_length=100)
    customer_phone: str | None = Field(default=None, min_length=5, max_length=32)
    customer_email: EmailStr | None = None
    comment: str | None = Field(default=None, max_length=500)
    internal_comment: str | None = Field(default=None, max_length=500)
    delivery_date: date | None = None
    delivery_time_slot_id: int | None = Field(default=None, gt=0)

    @field_validator("customer_name", mode="before")
    @classmethod
    def normalize_customer_name(cls, value):
        if value is None:
            return value
        return " ".join(value.strip().split())

    @field_validator("comment", "internal_comment", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value):
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @field_validator("customer_phone", mode="before")
    @classmethod
    def normalize_customer_phone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return normalize_phone(value)


class AdminOrderUpdateResponse(BaseModel):
    id: int
    order_number: str
    customer_name: str
    customer_phone: str
    comment: str | None = None
    internal_comment: str | None = None
    updated_at: datetime


class AdminOrderConfirmRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=500)
    notify_customer: bool = False

    @field_validator("comment", mode="before")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class AdminOrderCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    notify_customer: bool = False
    release_stock: bool = True

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class AdminOrderSync1CRequest(BaseModel):
    force: bool = False


class AdminOrderSync1CResponse(BaseModel):
    order_id: int
    order_number: str
    sync_status: str
    external_1c_id: str | None = None
    last_sync_at: datetime | None = None


class AdminOrderActionShortResponse(BaseModel):
    id: int
    order_number: str
    status: str
    cancel_reason: str | None = None


class AdminOrderActionResponse(BaseModel):
    message: str
    order: AdminOrderActionShortResponse


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


class OrderAddressResponse(BaseModel):
    id: int
    city: str
    street: str
    house: str
    apartment: str | None = None
    comment: str | None = None


class OrderPickupPointResponse(BaseModel):
    id: int
    name: str


class OrderPaymentResponse(BaseModel):
    id: int
    amount: Decimal
    status: str
    payment_url: str | None = None


class OrderDetailResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_method: str | None = None
    payment_status: str | None = None
    delivery_type: str
    customer_name: str
    customer_phone: str
    customer_email: EmailStr | None = None
    address: OrderAddressResponse | None = None
    pickup_point: OrderPickupPointResponse | None = None
    payment: OrderPaymentResponse | None = None
    items: list[OrderItemResponse]
    subtotal: Decimal
    discount_amount: Decimal
    promo_discount_amount: Decimal
    delivery_price: Decimal
    final_price: Decimal
    comment: str | None = None
    created_at: datetime
    updated_at: datetime


class OrderCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        from source.utils.order import normalize_cancel_reason

        return normalize_cancel_reason(value)


class OrderShortStatusResponse(BaseModel):
    id: int
    order_number: str
    status: str
    payment_status: str | None = None
    cancel_reason: str | None = None
    cancelled_at: datetime | None = None


class OrderCancelResponse(BaseModel):
    message: str
    order: OrderShortStatusResponse


class OrderNextActionResponse(BaseModel):
    type: str
    label: str


class OrderStatusResponse(BaseModel):
    id: int
    order_number: str
    status: str
    status_label: str
    payment_status: str | None = None
    payment_status_label: str | None = None
    delivery_type: str
    next_action: OrderNextActionResponse | None = None
    updated_at: datetime


class RepeatOrderRequest(BaseModel):
    replace_cart: bool = False


class RepeatOrderWarningResponse(BaseModel):
    product_id: int
    product_name: str
    reason: str
    requested_quantity: Decimal | None = None
    added_quantity: Decimal | None = None


class RepeatOrderResponse(BaseModel):
    message: str
    cart: "CartResponse"
    warnings: list[RepeatOrderWarningResponse]


from source.schemas.pydantic.cart import CartResponse

RepeatOrderResponse.model_rebuild()
