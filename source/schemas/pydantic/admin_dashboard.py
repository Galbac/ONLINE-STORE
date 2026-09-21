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


class PaymentSplitItem(BaseModel):
    method: str
    label: str
    count: int
    amount: Decimal
    share_percent: float


class DeliverySplitItem(BaseModel):
    type: str
    label: str
    count: int
    amount: Decimal
    share_percent: float


class StatusFunnelItem(BaseModel):
    status: str
    label: str
    count: int
    share_percent: float


class CategorySalesItem(BaseModel):
    category_id: int
    category_name: str
    orders_count: int
    total_amount: Decimal
    share_percent: float


class TopProductItem(BaseModel):
    id: int
    name: str
    category_name: str | None = None
    sold_quantity: Decimal
    total_sales: Decimal
    current_stock: Decimal
    unit: str
    abc_group: str = "A"
    xyz_group: str = "X"


class MarketBasketPairItem(BaseModel):
    product_a: str
    product_b: str
    frequency: int


class RfmSegmentationSummary(BaseModel):
    vip_count: int = 0
    regular_count: int = 0
    at_risk_count: int = 0
    newbies_count: int = 0


class SubstitutionSplitItem(BaseModel):
    policy: str
    label: str
    count: int
    share_percent: float


class PromoCodeAnalyticsItem(BaseModel):
    code: str
    name: str | None = None
    uses_count: int
    total_discount: Decimal


class StockAlertProductItem(BaseModel):
    product_id: int
    product_name: str
    waiting_users_count: int


class CourierRatingItem(BaseModel):
    id: int
    name: str
    delivered_orders_count: int
    tips_amount: Decimal = Decimal("0.00")
    rating: float = 4.9


class LoyaltyAnalyticsSummary(BaseModel):
    total_points_accrued: int
    total_points_spent: int
    active_accounts_count: int
    points_payment_share_percent: float = Field(default=0.0)


class ZoneSalesItem(BaseModel):
    zone_id: int | None = None
    zone_name: str
    orders_count: int
    total_amount: Decimal
    share_percent: float


class DeadStockItem(BaseModel):
    id: int
    name: str
    stock_quantity: Decimal
    price: Decimal
    unit: str


class HourlySalesItem(BaseModel):
    hour: int
    orders_count: int
    amount: Decimal


class CustomerAnalytics(BaseModel):
    total_customers: int
    new_customers: int
    repeat_customers: int
    repeat_purchase_rate: float
    avg_items_per_order: float
    average_ltv: Decimal = Field(default=Decimal("0.00"))


class InventorySummary(BaseModel):
    total_products: int
    out_of_stock_count: int
    low_stock_count: int
    total_stock_value: Decimal
    active_stock_alerts: int
    estimated_lost_revenue: Decimal = Field(default=Decimal("0.00"))
    turnover_days: int = 14
    top_stock_alerts: list[StockAlertProductItem] = Field(default_factory=list)


class RetentionCohortItem(BaseModel):
    cohort_name: str
    users_count: int
    m0: float = 100.0
    m1: float = 0.0
    m2: float = 0.0
    m3: float = 0.0


class OperationsAnalytics(BaseModel):
    picking_minutes: int = 12
    transit_minutes: int = 18
    total_lifecycle_minutes: int = 30
    cancel_rate_percent: float = 0.0
    csat_score: float = 4.8
    total_reviews_count: int = 0
    total_tips_amount: Decimal = Field(default=Decimal("0.00"))
    top_couriers: list[CourierRatingItem] = Field(default_factory=list)


class FinancialSummary(BaseModel):
    total_revenue: Decimal
    gmv: Decimal = Field(default=Decimal("0.00"))
    net_revenue: Decimal = Field(default=Decimal("0.00"))
    refunds_amount: Decimal = Field(default=Decimal("0.00"))
    orders_count: int
    paid_orders_count: int
    average_order_value: Decimal
    aov_delivery: Decimal = Field(default=Decimal("0.00"))
    aov_pickup: Decimal = Field(default=Decimal("0.00"))
    total_discount: Decimal
    total_promo_discount: Decimal
    promo_depth_percent: float = Field(default=0.0)
    acquiring_saved_amount: Decimal = Field(default=Decimal("0.00"))
    currency: str = "RUB"


class AdminAnalyticsResponse(BaseModel):
    date_from: date
    date_to: date
    period: str
    financial: FinancialSummary
    payment_breakdown: list[PaymentSplitItem]
    delivery_breakdown: list[DeliverySplitItem]
    status_funnel: list[StatusFunnelItem]
    category_sales: list[CategorySalesItem]
    top_products: list[TopProductItem]
    dead_stock: list[DeadStockItem] = Field(default_factory=list)
    zone_sales: list[ZoneSalesItem] = Field(default_factory=list)
    promo_codes: list[PromoCodeAnalyticsItem] = Field(default_factory=list)
    loyalty: LoyaltyAnalyticsSummary = Field(
        default_factory=lambda: LoyaltyAnalyticsSummary(
            total_points_accrued=0, total_points_spent=0, active_accounts_count=0
        )
    )
    operations: OperationsAnalytics = Field(default_factory=OperationsAnalytics)
    market_basket: list[MarketBasketPairItem] = Field(default_factory=list)
    rfm_segments: RfmSegmentationSummary = Field(default_factory=RfmSegmentationSummary)
    retention_cohorts: list[RetentionCohortItem] = Field(default_factory=list)
    substitution_split: list[SubstitutionSplitItem] = Field(default_factory=list)
    hourly_distribution: list[HourlySalesItem]
    customers: CustomerAnalytics
    inventory: InventorySummary
    sales_timeline: list[AdminSalesSeriesItem]
