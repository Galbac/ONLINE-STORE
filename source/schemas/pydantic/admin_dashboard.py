from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from source.config.settings import settings
from source.utils.date_range import validate_date_range


class AdminDashboardOrdersStats(BaseModel):
    today_count: int
    new_count: int
    paid_today_count: int


class AdminDashboardSalesStats(BaseModel):
    today_amount: Decimal
    currency: str


class AdminDashboardProductsStats(BaseModel):
    low_stock_count: int
    total_active: int


class AdminDashboardUsersStats(BaseModel):
    total: int


class AdminRecentOrderResponse(BaseModel):
    id: int
    order_number: str
    status: str
    final_price: Decimal
    created_at: datetime


class AdminPopularProductResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    popularity: int


class AdminDashboardResponse(BaseModel):
    orders: AdminDashboardOrdersStats
    sales: AdminDashboardSalesStats
    products: AdminDashboardProductsStats
    users: AdminDashboardUsersStats
    recent_orders: list[AdminRecentOrderResponse]
    popular_products: list[AdminPopularProductResponse]


class AdminSalesQueryParams(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    group_by: Literal["day", "week", "month"] = "day"

    @model_validator(mode="after")
    def set_defaults_and_validate_dates(self) -> "AdminSalesQueryParams":
        today = datetime.now(settings.tz).date()
        if self.date_to is None:
            self.date_to = today
        if self.date_from is None:
            self.date_from = self.date_to - timedelta(days=29)
        validate_date_range(date_from=self.date_from, date_to=self.date_to)
        return self


class AdminSalesSeriesItem(BaseModel):
    date: date
    amount: Decimal
    orders_count: int


class AdminSalesResponse(BaseModel):
    date_from: date
    date_to: date
    group_by: Literal["day", "week", "month"]
    total_amount: Decimal = Field(default=Decimal("0.00"))
    orders_count: int
    average_order_value: Decimal = Field(default=Decimal("0.00"))
    series: list[AdminSalesSeriesItem]


class AdminLowStockQueryParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    category_id: int | None = Field(default=None, ge=1)


class AdminLowStockProductResponse(BaseModel):
    id: int
    name: str
    sku: str | None = None
    unit: str
    product_type: str
    stock_quantity: Decimal
    low_stock_threshold: Decimal
    is_available: bool


class AdminLowStockResponse(BaseModel):
    items: list[AdminLowStockProductResponse]
    total: int
    limit: int
    offset: int
