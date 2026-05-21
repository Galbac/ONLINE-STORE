from decimal import Decimal
from datetime import date as date_type, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from source.schemas.pydantic.product import ProductType


OneCOrderSyncStatus = Literal["pending", "pending_update", "pending_cancel", "error"]


class OneCCategoryImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_1c_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    parent_external_1c_id: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    sort_order: int = 0

    @field_validator("external_1c_id", "name", "slug", "parent_external_1c_id", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class OneCCategoryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OneCCategoryImportItem]


class OneCProductImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_1c_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, max_length=100)
    category_external_1c_id: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=20)
    product_type: ProductType
    quantity_step: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    min_quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    is_active: bool = True
    is_available: bool = True

    @field_validator("external_1c_id", "name", "sku", "barcode", "category_external_1c_id", "unit", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @model_validator(mode="after")
    def validate_quantity_rules(self) -> "OneCProductImportItem":
        if self.product_type == "piece":
            if self.quantity_step != self.quantity_step.to_integral_value():
                raise ValueError("quantity_step for piece product must be integer")
            if self.min_quantity != self.min_quantity.to_integral_value():
                raise ValueError("min_quantity for piece product must be integer")
        return self


class OneCProductImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OneCProductImportItem]


class OneCPriceImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_external_1c_id: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(max_digits=12, decimal_places=2)
    old_price: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("product_external_1c_id", "currency", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        if not normalized_value:
            return None
        return normalized_value.upper() if len(normalized_value) == 3 else normalized_value


class OneCPriceImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OneCPriceImportItem]


class OneCStockImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_external_1c_id: str = Field(min_length=1, max_length=100)
    stock_quantity: Decimal = Field(max_digits=12, decimal_places=3)
    reserved_quantity: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    warehouse_external_1c_id: str | None = Field(default=None, max_length=100)

    @field_validator("product_external_1c_id", "warehouse_external_1c_id", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class OneCStockImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OneCStockImportItem]


class OneCImageImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_external_1c_id: str = Field(min_length=1, max_length=100)
    image_external_1c_id: str | None = Field(default=None, max_length=100)
    image_url: str | None = Field(default=None, max_length=1000)
    filename: str | None = Field(default=None, max_length=255)
    content_base64: str | None = None
    sort_order: int = 0
    is_main: bool = False

    @field_validator("product_external_1c_id", "image_external_1c_id", "image_url", "filename", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class OneCImageImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OneCImageImportItem]


class OneCImportItemErrorResponse(BaseModel):
    external_1c_id: str | None = None
    product_external_1c_id: str | None = None
    message: str
    field: str | None = None


class AdminOneCSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_sync: bool = False


class OneCImportResultResponse(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[OneCImportItemErrorResponse] = Field(default_factory=list)


class AdminOneCSyncResponse(BaseModel):
    status: Literal["started", "success", "error"]
    job_id: int
    message: str | None = None
    created: int | None = None
    updated: int | None = None
    errors: list[OneCImportItemErrorResponse] | None = None


class AdminOneCOrderSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    only_errors: bool = False


class AdminOneCOrderSyncResponse(BaseModel):
    status: Literal["success"]
    job_id: int
    processed: int
    synced: int
    errors: int


OneCLogDirection = Literal["inbound", "outbound"]
OneCLogEntityType = Literal["categories", "products", "prices", "stocks", "images", "orders"]
OneCLogStatus = Literal["success", "partial", "error", "started"]


class AdminOneCLogsQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    direction: OneCLogDirection | None = None
    entity_type: OneCLogEntityType | None = None
    status: OneCLogStatus | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    q: str | None = Field(default=None, max_length=255)

    @field_validator("q", mode="before")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @model_validator(mode="after")
    def validate_date_range(self) -> "AdminOneCLogsQueryParams":
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from не может быть больше date_to")
        return self


class AdminOneCLogItemResponse(BaseModel):
    id: int
    direction: OneCLogDirection
    entity_type: OneCLogEntityType
    status: OneCLogStatus
    message: str | None = None
    created_count: int = 0
    updated_count: int = 0
    error_count: int = 0
    created_at: datetime
    request_payload: dict | None = None
    response_payload: dict | None = None


class AdminOneCLogsResponse(BaseModel):
    items: list[AdminOneCLogItemResponse]
    total: int
    page: int
    limit: int
    pages: int


class OneCOrdersPendingQueryParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    status: OneCOrderSyncStatus | None = None


class OneCOrderCustomerResponse(BaseModel):
    name: str
    phone: str
    email: str | None = None


class OneCOrderDeliveryResponse(BaseModel):
    type: str
    address: str | None = None
    date: date_type | None = None
    time_slot: str | None = None
    pickup_point: str | None = None


class OneCOrderPaymentResponse(BaseModel):
    method: str | None = None
    status: str | None = None


class OneCOrderItemResponse(BaseModel):
    product_id: int
    product_external_1c_id: str | None = None
    name: str
    quantity: Decimal
    unit: str
    price: Decimal
    final_price: Decimal


class OneCOrderTotalsResponse(BaseModel):
    subtotal: Decimal
    discount_amount: Decimal
    promo_discount_amount: Decimal
    delivery_price: Decimal
    final_price: Decimal


class OneCOrderPayloadResponse(BaseModel):
    id: int
    order_number: str
    status: str
    sync_status: str
    customer: OneCOrderCustomerResponse
    delivery: OneCOrderDeliveryResponse
    payment: OneCOrderPaymentResponse
    items: list[OneCOrderItemResponse]
    totals: OneCOrderTotalsResponse
    created_at: datetime | None = None


class OneCOrdersPendingResponse(BaseModel):
    items: list[OneCOrderPayloadResponse]
    total: int


class OneCMarkOrderSyncedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_1c_id: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None, max_length=500)

    @field_validator("external_1c_id", "message", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class OneCOrderSyncErrorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=2000)
    error_code: str | None = Field(default=None, max_length=100)

    @field_validator("error", mode="before")
    @classmethod
    def normalize_error(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip()

    @field_validator("error_code", mode="before")
    @classmethod
    def normalize_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class OneCOrderSyncResponse(BaseModel):
    order_id: int
    order_number: str
    sync_status: str
    external_1c_id: str | None = None
    sync_error: str | None = None
    sync_error_code: str | None = None
    last_sync_at: datetime | None = None
