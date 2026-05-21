import os
from datetime import tzinfo
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    production: bool = False


class ProjectName(BaseModel):
    title: str = "Grocery Store API"
    path: str = ""
    slug: str = "grocery_store"


class AppSettings(BaseSettings):
    name: str = Field(default="supermarket-api", alias="APP_NAME")
    version: str = Field(default="0.1.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="APP_ENV")
    health_show_environment: bool = Field(default=False, alias="HEALTH_SHOW_ENVIRONMENT")
    health_db_timeout_seconds: int = Field(default=3, alias="HEALTH_DB_TIMEOUT_SECONDS")
    health_protect_internal_endpoints: bool = Field(default=False, alias="HEALTH_PROTECT_INTERNAL_ENDPOINTS")
    health_internal_token: str = Field(default="", alias="HEALTH_INTERNAL_TOKEN")
    health_storage_timeout_seconds: int = Field(default=5, alias="HEALTH_STORAGE_TIMEOUT_SECONDS")
    health_storage_check_write: bool = Field(default=False, alias="HEALTH_STORAGE_CHECK_WRITE")
    health_1c_cache_ttl_seconds: int = Field(default=30, alias="HEALTH_1C_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ApiV1Prefix(BaseModel):
    prefix: str = "/v1"


class ApiPrefix(BaseModel):
    prefix: str = "/api"
    v1: ApiV1Prefix = ApiV1Prefix()


class DbSettings(BaseModel):
    url: str | PostgresDsn | None = None
    test_url: str | PostgresDsn | None = None
    echo: bool = False
    echo_pool: bool = False
    max_overflow: int = 10
    pool_size: int = 5
    naming_convention: dict[str, str] = {
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

    @staticmethod
    def _read_secret_or_env(
        secret_name: str,
        env_var_name: str,
        default: str = "postgres",
    ) -> str:
        run_secret = Path("/run/secrets") / secret_name
        if secret_name and run_secret.exists() and run_secret.is_file():
            return run_secret.read_text().strip()
        return os.getenv(env_var_name, default)

    @classmethod
    def create_url(
        cls,
        user_secret_name: str,
        password_secret_name: str,
        db_name: Optional[str] = None,
    ) -> str:
        db = db_name or os.getenv("POSTGRES_DB", "postgres")
        user = cls._read_secret_or_env(user_secret_name, "POSTGRES_USER", "postgres")
        password = cls._read_secret_or_env(password_secret_name, "POSTGRES_PASSWORD", "postgres")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        return f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"

    @classmethod
    def create_test_url(
        cls,
        user_secret_name: str,
        password_secret_name: str,
    ) -> str:
        return cls.create_url(
            user_secret_name=user_secret_name,
            password_secret_name=password_secret_name,
            db_name="test_database",
        )

    def __init__(self, **kwargs):
        user_secret_name = os.getenv("PSQL_USER_SECRET_NAME", "")
        password_secret_name = os.getenv("PSQL_PASSWORD_SECRET_NAME", "")
        kwargs.setdefault(
            "url",
            type(self).create_url(
                user_secret_name=user_secret_name,
                password_secret_name=password_secret_name,
            ),
        )
        kwargs.setdefault(
            "test_url",
            type(self).create_test_url(
                user_secret_name=user_secret_name,
                password_secret_name=password_secret_name,
            ),
        )
        super().__init__(**kwargs)


class MiddlewareSettings(BaseModel):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost", "http://localhost:3000"])
    allow_credentials: bool = True
    allow_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    allow_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type", "X-Telegram-Init-Data"],
    )


class AuthSettings(BaseSettings):
    jwt_secret_key: str = Field(
        default="change-me-in-env",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_minutes: int = Field(
        default=60 * 24 * 30,
        alias="JWT_REFRESH_TOKEN_EXPIRE_MINUTES",
    )
    refresh_rotation_enabled: bool = Field(default=True, alias="JWT_REFRESH_ROTATION_ENABLED")
    refresh_reuse_detection_enabled: bool = Field(default=True, alias="JWT_REFRESH_REUSE_DETECTION_ENABLED")
    refresh_rate_limit_per_minute: int = Field(default=20, alias="AUTH_REFRESH_RATE_LIMIT_PER_MINUTE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class SmtpSettings(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""


class EmailNotificationSettings(BaseSettings):
    enabled: bool = Field(default=False, alias="EMAIL_ENABLED")
    host: str = Field(default="", alias="EMAIL_HOST")
    port: int = Field(default=587, alias="EMAIL_PORT")
    username: str = Field(default="", alias="EMAIL_USERNAME")
    password: str = Field(default="", alias="EMAIL_PASSWORD")
    from_email: str = Field(default="", alias="EMAIL_FROM")
    use_tls: bool = Field(default=True, alias="EMAIL_USE_TLS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class TelegramSettings(BaseSettings):
    enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    admin_chat_id: str = Field(default="", alias="TELEGRAM_ADMIN_CHAT_ID")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class WebSettings(BaseModel):
    jwt_secret: str = ""
    jwt_expiry_hours: int = 72
    cabinet_base_url: str = ""


class RedisSettings(BaseSettings):
    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class PasswordResetSettings(BaseSettings):
    token_ttl_seconds: int = Field(default=1800, alias="PASSWORD_RESET_TOKEN_TTL_SECONDS")
    frontend_url: str = Field(default="https://site.ru/reset-password", alias="PASSWORD_RESET_FRONTEND_URL")
    rate_limit_by_login: int = Field(default=3, alias="PASSWORD_RESET_RATE_LIMIT_BY_LOGIN")
    rate_limit_by_ip: int = Field(default=10, alias="PASSWORD_RESET_RATE_LIMIT_BY_IP")
    rate_limit_window_seconds: int = Field(default=3600, alias="PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS")
    token_secret: str = Field(default="change-me-in-env", alias="PASSWORD_RESET_TOKEN_SECRET")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ChangePasswordSettings(BaseSettings):
    rate_limit_by_user: int = Field(default=5, alias="CHANGE_PASSWORD_RATE_LIMIT_BY_USER")
    rate_limit_by_ip: int = Field(default=10, alias="CHANGE_PASSWORD_RATE_LIMIT_BY_IP")
    rate_limit_window_seconds: int = Field(default=3600, alias="CHANGE_PASSWORD_RATE_LIMIT_WINDOW_SECONDS")
    failed_limit: int = Field(default=5, alias="CHANGE_PASSWORD_FAILED_LIMIT")
    failed_window_seconds: int = Field(default=900, alias="CHANGE_PASSWORD_FAILED_WINDOW_SECONDS")
    jwt_access_blacklist_enabled: bool = Field(default=False, alias="JWT_ACCESS_BLACKLIST_ENABLED")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AuthMeSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="AUTH_ME_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AdminAuthSettings(BaseSettings):
    login_failed_limit: int = Field(default=5, alias="ADMIN_LOGIN_FAILED_LIMIT")
    login_failed_window_seconds: int = Field(default=900, alias="ADMIN_LOGIN_FAILED_WINDOW_SECONDS")
    access_expire_minutes: int = Field(default=30, alias="JWT_ACCESS_EXPIRE_MINUTES")
    refresh_expire_days: int = Field(default=30, alias="JWT_REFRESH_EXPIRE_DAYS")
    me_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_AUTH_ME_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AdminDashboardSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=60, alias="ADMIN_DASHBOARD_CACHE_TTL_SECONDS")
    sales_cache_ttl_seconds: int = Field(default=300, alias="ADMIN_DASHBOARD_SALES_CACHE_TTL_SECONDS")
    low_stock_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_DASHBOARD_LOW_STOCK_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AdminSettingsSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=600, alias="ADMIN_SETTINGS_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AdminUsersSettings(BaseSettings):
    list_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_USERS_LIST_CACHE_TTL_SECONDS")
    detail_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_USERS_DETAIL_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AdminStaffSettings(BaseSettings):
    list_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_STAFF_LIST_CACHE_TTL_SECONDS")
    roles_cache_ttl_seconds: int = Field(default=300, alias="ADMIN_ROLES_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class UserMeSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="USER_ME_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class UserDeleteSettings(BaseSettings):
    require_password: bool = Field(default=True, alias="USER_DELETE_REQUIRE_PASSWORD")
    anonymize: bool = Field(default=False, alias="USER_DELETE_ANONYMIZE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProfileSummarySettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="PROFILE_SUMMARY_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProfileAddressesSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="PROFILE_ADDRESSES_CACHE_TTL_SECONDS")
    user_addresses_limit: int = Field(default=20, alias="USER_ADDRESSES_LIMIT")
    address_delete_soft: bool = Field(default=True, alias="ADDRESS_DELETE_SOFT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProfileOrdersSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=60, alias="PROFILE_ORDERS_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class CartSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="CART_CACHE_TTL_SECONDS")
    summary_cache_ttl_seconds: int = Field(default=120, alias="CART_SUMMARY_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OrdersSettings(BaseSettings):
    number_prefix: str = Field(default="ORD", alias="ORDER_NUMBER_PREFIX")
    default_status: str = Field(default="new", alias="ORDER_DEFAULT_STATUS")
    online_payment_status: str = Field(default="pending_payment", alias="ORDER_ONLINE_PAYMENT_STATUS")
    admin_list_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_ORDERS_LIST_CACHE_TTL_SECONDS")
    admin_detail_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_ORDERS_DETAIL_CACHE_TTL_SECONDS")
    cancel_allowed_statuses_raw: str = Field(
        default="new,pending_payment,confirmed,awaiting_confirmation",
        alias="ORDER_CANCEL_ALLOWED_STATUSES",
    )
    repeat_add_available_partial_quantity: bool = Field(
        default=True,
        alias="ORDER_REPEAT_ADD_AVAILABLE_PARTIAL_QUANTITY",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cancel_allowed_statuses(self) -> set[str]:
        return {status.strip() for status in self.cancel_allowed_statuses_raw.split(",") if status.strip()}


class OrdersMySettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=60, alias="ORDERS_MY_CACHE_TTL_SECONDS")
    default_limit: int = Field(default=20, alias="ORDERS_MY_DEFAULT_LIMIT")
    max_limit: int = Field(default=100, alias="ORDERS_MY_MAX_LIMIT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OrderDetailSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=60, alias="ORDER_DETAIL_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OrderStatusSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=30, alias="ORDER_STATUS_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OneCSettings(BaseSettings):
    sync_enabled: bool = Field(default=True, alias="ONE_C_SYNC_ENABLED")
    api_url: str = Field(default="", alias="ONE_C_API_URL")
    api_token: str = Field(default="", alias="ONE_C_API_TOKEN")
    import_max_batch_size: int = Field(default=1000, alias="ONE_C_IMPORT_MAX_BATCH_SIZE")
    health_timeout_seconds: int = Field(default=5, alias="ONE_C_HEALTH_TIMEOUT_SECONDS")
    auto_availability_from_stock: bool = Field(default=True, alias="AUTO_AVAILABILITY_FROM_STOCK")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class PaymentsSettings(BaseSettings):
    auto_refund_enabled: bool = Field(default=False, alias="AUTO_REFUND_ENABLED")
    provider: str = Field(default="yookassa", alias="PAYMENT_PROVIDER")
    currency: str = Field(default="RUB", alias="PAYMENT_CURRENCY")
    return_url: str = Field(default="https://site.ru/payment/success", alias="PAYMENT_RETURN_URL")
    fail_url: str = Field(default="https://site.ru/payment/fail", alias="PAYMENT_FAIL_URL")
    webhook_url: str = Field(default="https://api.site.ru/api/payments/webhook", alias="PAYMENT_WEBHOOK_URL")
    provider_shop_id: str = Field(default="", alias="PAYMENT_PROVIDER_SHOP_ID")
    provider_secret_key: str = Field(default="", alias="PAYMENT_PROVIDER_SECRET_KEY")
    detail_cache_ttl_seconds: int = Field(default=30, alias="PAYMENT_DETAIL_CACHE_TTL_SECONDS")
    status_sync_enabled: bool = Field(default=False, alias="PAYMENT_STATUS_SYNC_ENABLED")
    capture_mode: str = Field(default="automatic", alias="PAYMENT_CAPTURE_MODE")
    provider_webhook_secret: str = Field(default="", alias="PAYMENT_PROVIDER_WEBHOOK_SECRET")
    webhook_verify_signature: bool = Field(default=True, alias="PAYMENT_WEBHOOK_VERIFY_SIGNATURE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class CategoriesSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=600, alias="CATEGORIES_LIST_CACHE_TTL_SECONDS")
    admin_list_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_CATEGORIES_LIST_CACHE_TTL_SECONDS")
    tree_cache_ttl_seconds: int = Field(default=600, alias="CATEGORIES_TREE_CACHE_TTL_SECONDS")
    tree_max_depth_default: int = Field(default=3, alias="CATEGORIES_TREE_MAX_DEPTH_DEFAULT")
    detail_cache_ttl_seconds: int = Field(default=600, alias="CATEGORY_DETAIL_CACHE_TTL_SECONDS")
    slug_cache_ttl_seconds: int = Field(default=600, alias="CATEGORY_SLUG_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProductsSettings(BaseSettings):
    list_cache_ttl_seconds: int = Field(default=120, alias="PRODUCTS_LIST_CACHE_TTL_SECONDS")
    admin_list_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_PRODUCTS_LIST_CACHE_TTL_SECONDS")
    admin_detail_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_PRODUCTS_DETAIL_CACHE_TTL_SECONDS")
    detail_cache_ttl_seconds: int = Field(default=180, alias="PRODUCT_DETAIL_CACHE_TTL_SECONDS")
    slug_cache_ttl_seconds: int = Field(default=180, alias="PRODUCT_SLUG_CACHE_TTL_SECONDS")
    search_cache_ttl_seconds: int = Field(default=60, alias="PRODUCT_SEARCH_CACHE_TTL_SECONDS")
    search_min_query_length: int = Field(default=2, alias="PRODUCT_SEARCH_MIN_QUERY_LENGTH")
    search_max_query_length: int = Field(default=100, alias="PRODUCT_SEARCH_MAX_QUERY_LENGTH")
    popular_cache_ttl_seconds: int = Field(default=600, alias="PRODUCT_POPULAR_CACHE_TTL_SECONDS")
    popular_default_limit: int = Field(default=12, alias="PRODUCT_POPULAR_DEFAULT_LIMIT")
    discounted_cache_ttl_seconds: int = Field(default=120, alias="PRODUCT_DISCOUNTED_CACHE_TTL_SECONDS")
    new_cache_ttl_seconds: int = Field(default=600, alias="PRODUCT_NEW_CACHE_TTL_SECONDS")
    new_default_limit: int = Field(default=12, alias="PRODUCT_NEW_DEFAULT_LIMIT")
    new_default_days: int = Field(default=30, alias="PRODUCT_NEW_DEFAULT_DAYS")
    similar_cache_ttl_seconds: int = Field(default=600, alias="PRODUCT_SIMILAR_CACHE_TTL_SECONDS")
    similar_default_limit: int = Field(default=8, alias="PRODUCT_SIMILAR_DEFAULT_LIMIT")
    list_default_limit: int = Field(default=24, alias="PRODUCTS_LIST_DEFAULT_LIMIT")
    list_max_limit: int = Field(default=100, alias="PRODUCTS_LIST_MAX_LIMIT")
    piece_stock_integer_required: bool = Field(default=True, alias="PRODUCT_PIECE_STOCK_INTEGER_REQUIRED")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DeliveryOptionsSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=600, alias="DELIVERY_OPTIONS_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DeliveryCalculateSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="DELIVERY_CALCULATE_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DeliveryPickupPointsSettings(BaseSettings):
    list_cache_ttl_seconds: int = Field(default=600, alias="DELIVERY_PICKUP_POINTS_CACHE_TTL_SECONDS")
    detail_cache_ttl_seconds: int = Field(default=600, alias="DELIVERY_PICKUP_POINT_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DeliveryTimeSlotsSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="DELIVERY_TIME_SLOTS_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AdminDeliverySettings(BaseSettings):
    settings_cache_ttl_seconds: int = Field(default=600, alias="ADMIN_DELIVERY_SETTINGS_CACHE_TTL_SECONDS")
    zones_cache_ttl_seconds: int = Field(default=300, alias="ADMIN_DELIVERY_ZONES_CACHE_TTL_SECONDS")
    pickup_points_cache_ttl_seconds: int = Field(default=300, alias="ADMIN_DELIVERY_PICKUP_POINTS_CACHE_TTL_SECONDS")
    supported_currencies_raw: str = Field(default="RUB", alias="SUPPORTED_CURRENCIES")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def supported_currencies(self) -> set[str]:
        return {currency.strip().upper() for currency in self.supported_currencies_raw.split(",") if currency.strip()}


class DiscountsSettings(BaseSettings):
    active_cache_ttl_seconds: int = Field(default=120, alias="DISCOUNTS_ACTIVE_CACHE_TTL_SECONDS")
    products_cache_ttl_seconds: int = Field(default=120, alias="DISCOUNT_PRODUCTS_CACHE_TTL_SECONDS")
    admin_list_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_DISCOUNTS_LIST_CACHE_TTL_SECONDS")
    admin_detail_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_DISCOUNTS_DETAIL_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class PromoCodesSettings(BaseSettings):
    admin_list_cache_ttl_seconds: int = Field(default=60, alias="ADMIN_PROMO_CODES_LIST_CACHE_TTL_SECONDS")
    admin_detail_cache_ttl_seconds: int = Field(default=120, alias="ADMIN_PROMO_CODES_DETAIL_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class FavoritesSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="FAVORITES_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class NotificationsSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=60, alias="NOTIFICATIONS_CACHE_TTL_SECONDS")
    default_limit: int = Field(default=20, alias="NOTIFICATIONS_DEFAULT_LIMIT")
    max_limit: int = Field(default=100, alias="NOTIFICATIONS_MAX_LIMIT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class MediaSettings(BaseSettings):
    storage: str = Field(default="local", alias="MEDIA_STORAGE")
    root: Path = Field(default=Path("/app/media"), alias="MEDIA_ROOT")
    url: str = Field(default="/media", alias="MEDIA_URL")
    max_image_size_mb: int = Field(default=5, alias="MEDIA_MAX_IMAGE_SIZE_MB")
    allowed_image_types: str = Field(
        default="image/jpeg,image/png,image/webp",
        alias="MEDIA_ALLOWED_IMAGE_TYPES",
    )
    allowed_image_extensions: str = Field(
        default=".jpg,.jpeg,.png,.webp",
        alias="MEDIA_ALLOWED_IMAGE_EXTENSIONS",
    )
    base_url: str = Field(default="", alias="MEDIA_BASE_URL")
    storage_access_key: str = Field(default="", alias="STORAGE_ACCESS_KEY")
    storage_secret_key: str = Field(default="", alias="STORAGE_SECRET_KEY")
    storage_bucket: str = Field(default="", alias="STORAGE_BUCKET")
    storage_region: str = Field(default="", alias="STORAGE_REGION")
    detail_cache_ttl_seconds: int = Field(default=300, alias="UPLOAD_DETAIL_CACHE_TTL_SECONDS")

    @property
    def allowed_image_type_set(self) -> set[str]:
        return {item.strip() for item in self.allowed_image_types.split(",") if item.strip()}

    @property
    def allowed_image_extension_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_image_extensions.split(",") if item.strip()}

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="FASTAPI_CFG__",
        extra="ignore",
    )
    run: RunConfig = RunConfig()
    app: AppSettings = AppSettings()
    names: ProjectName = ProjectName()
    api: ApiPrefix = ApiPrefix()
    db: DbSettings = DbSettings()
    auth: AuthSettings = AuthSettings()
    middleware: MiddlewareSettings = MiddlewareSettings()
    smtp: SmtpSettings = SmtpSettings()
    email_notifications: EmailNotificationSettings = EmailNotificationSettings()
    telegram: TelegramSettings = TelegramSettings()
    web: WebSettings = WebSettings()
    redis: RedisSettings = RedisSettings()
    password_reset: PasswordResetSettings = PasswordResetSettings()
    change_password: ChangePasswordSettings = ChangePasswordSettings()
    auth_me: AuthMeSettings = AuthMeSettings()
    admin_auth: AdminAuthSettings = AdminAuthSettings()
    admin_dashboard: AdminDashboardSettings = AdminDashboardSettings()
    admin_settings: AdminSettingsSettings = AdminSettingsSettings()
    admin_users: AdminUsersSettings = AdminUsersSettings()
    admin_staff: AdminStaffSettings = AdminStaffSettings()
    user_me: UserMeSettings = UserMeSettings()
    user_delete: UserDeleteSettings = UserDeleteSettings()
    profile_summary: ProfileSummarySettings = ProfileSummarySettings()
    profile_addresses: ProfileAddressesSettings = ProfileAddressesSettings()
    profile_orders: ProfileOrdersSettings = ProfileOrdersSettings()
    cart: CartSettings = CartSettings()
    orders: OrdersSettings = OrdersSettings()
    orders_my: OrdersMySettings = OrdersMySettings()
    order_detail: OrderDetailSettings = OrderDetailSettings()
    order_status: OrderStatusSettings = OrderStatusSettings()
    one_c: OneCSettings = OneCSettings()
    payments: PaymentsSettings = PaymentsSettings()
    categories: CategoriesSettings = CategoriesSettings()
    products: ProductsSettings = ProductsSettings()
    delivery_options: DeliveryOptionsSettings = DeliveryOptionsSettings()
    delivery_calculate: DeliveryCalculateSettings = DeliveryCalculateSettings()
    delivery_pickup_points: DeliveryPickupPointsSettings = DeliveryPickupPointsSettings()
    delivery_time_slots: DeliveryTimeSlotsSettings = DeliveryTimeSlotsSettings()
    admin_delivery: AdminDeliverySettings = AdminDeliverySettings()
    discounts: DiscountsSettings = DiscountsSettings()
    promo_codes: PromoCodesSettings = PromoCodesSettings()
    favorites: FavoritesSettings = FavoritesSettings()
    notifications: NotificationsSettings = NotificationsSettings()
    media: MediaSettings = MediaSettings()

    @property
    def tz(self) -> tzinfo:
        return ZoneInfo("Europe/Moscow")


settings = Settings()
