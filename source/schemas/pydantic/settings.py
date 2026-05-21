from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from source.utils.user_profile import validate_email, validate_phone


class AdminSettingsResponse(BaseModel):
    shop_name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    working_hours: str | None = None
    default_city: str | None = None
    currency: str
    delivery_enabled: bool
    pickup_enabled: bool
    online_payment_enabled: bool
    pay_on_delivery_enabled: bool
    min_order_amount: Decimal
    maintenance_mode: bool
    updated_at: datetime | None = None


class AdminSettingsUpdateRequest(BaseModel):
    shop_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    working_hours: str | None = Field(default=None, max_length=255)
    default_city: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    delivery_enabled: bool | None = None
    pickup_enabled: bool | None = None
    online_payment_enabled: bool | None = None
    pay_on_delivery_enabled: bool | None = None
    min_order_amount: Decimal | None = None
    maintenance_mode: bool | None = None

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "AdminSettingsUpdateRequest":
        for field in (
            "shop_name",
            "delivery_enabled",
            "pickup_enabled",
            "online_payment_enabled",
            "pay_on_delivery_enabled",
            "min_order_amount",
            "maintenance_mode",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        for field in ("shop_name", "phone", "email", "address", "working_hours", "default_city", "currency"):
            value = getattr(self, field)
            if value is not None:
                value = value.strip()
                setattr(self, field, value or None)
        if self.shop_name is not None and not self.shop_name:
            raise ValueError("shop_name обязателен")
        if self.email is not None:
            self.email = validate_email(self.email)
        if self.phone is not None:
            self.phone = validate_phone(self.phone)
        if self.currency is not None:
            self.currency = self.currency.upper()
            if self.currency != "RUB":
                raise ValueError("Неподдерживаемая валюта")
        if self.min_order_amount is not None and self.min_order_amount < 0:
            raise ValueError("min_order_amount не может быть отрицательным")
        return self
