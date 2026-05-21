from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
