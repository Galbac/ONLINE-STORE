from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from source.schemas.pydantic.product import ProductType


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


class OneCImportItemErrorResponse(BaseModel):
    external_1c_id: str | None = None
    product_external_1c_id: str | None = None
    message: str
    field: str | None = None


class OneCImportResultResponse(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[OneCImportItemErrorResponse] = Field(default_factory=list)
