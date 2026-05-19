from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
