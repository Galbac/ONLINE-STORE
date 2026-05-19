from collections.abc import AsyncIterable

from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from source.common.commiter import Commiter
from source.config.settings import Settings, settings
from source.db.db_helper import db_helper
from source.db.sa_commiter import SACommiter
from source.interactors.auth_change_password import AuthChangePasswordInteractor
from source.interactors.auth_forgot_password import AuthForgotPasswordInteractor
from source.interactors.auth_login import AuthLoginInteractor
from source.interactors.auth_logout import AuthLogoutInteractor
from source.interactors.auth_me import AuthMeInteractor
from source.interactors.auth_refresh import AuthRefreshInteractor
from source.interactors.auth_register import AuthRegisterInteractor
from source.interactors.auth_reset_password import AuthResetPasswordInteractor
from source.repositories.address import AddressRepository
from source.repositories.admin_audit_log import AdminAuditLogRepository
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.category import CategoryRepository
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.delivery_time_slot import DeliveryTimeSlotRepository
from source.repositories.delivery_zone import DeliveryZoneRepository
from source.repositories.discount import DiscountRepository
from source.repositories.favorite import FavoriteRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.notification import NotificationLogRepository, NotificationRepository
from source.repositories.payment import PaymentRepository
from source.repositories.payment_webhook_log import PaymentWebhookLogRepository
from source.repositories.refund import RefundRepository
from source.repositories.refresh_token import RefreshTokenRepository
from source.repositories.pickup_point import PickupPointRepository
from source.repositories.product import ProductRepository
from source.repositories.product_availability_log import ProductAvailabilityLogRepository
from source.repositories.product_image import ProductImageRepository
from source.repositories.promo_code import PromoCodeRepository, PromoCodeUsageRepository
from source.repositories.stock_movement import StockMovementRepository
from source.repositories.user import UserRepository
from source.repositories.upload import UploadRepository
from source.services.auth_cache import AuthCacheService
from source.services.admin_auth import AdminAuthService, AuditLogService, JwtBlacklistService, JwtService, PermissionService, RateLimitService
from source.services.admin_auth_cache import AdminAuthCacheService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.admin_product import AdminProductService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.auth import AuthService
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.category import CategoryService
from source.services.category_cache import CategoryCacheService
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.delivery_cache import DeliveryCacheService
from source.services.notifications import NotificationService
from source.services.notification_cache import NotificationCacheService
from source.services.delivery import DeliveryService, DeliveryTimeSlotService, DeliveryZoneService
from source.services.discount import DiscountService
from source.services.discount_cache import DiscountCacheService
from source.services.favorite import FavoriteService
from source.services.favorite_cache import FavoriteCacheService
from source.services.one_c import OneCIntegrationService
from source.services.order import OrderService
from source.services.order_cache import OrderCacheService
from source.services.payment_cache import PaymentCacheService
from source.services.payment import PaymentProviderService, PaymentService
from source.services.payment_webhook import PaymentWebhookService
from source.services.product import ProductService
from source.services.product_cache import ProductCacheService
from source.services.profile import ProfileService
from source.services.profile_cache import ProfileCacheService
from source.services.redis import RedisService
from source.services.stock import StockMovementService, StockService
from source.services.promo_code import PromoCodeService
from source.services.user import UserService
from source.services.user_cache import UserCacheService
from source.services.storage import StorageService
from source.services.upload import UploadService
from source.services.upload_cache import UploadCacheService


class AppProvider(Provider):
    config = from_context(provides=Settings, scope=Scope.APP)

    sa_commiter = provide(
        SACommiter,
        scope=Scope.REQUEST,
        provides=Commiter,
    )
    auth_service = provide(
        AuthService,
        scope=Scope.REQUEST,
    )
    auth_register_interactor = provide(
        AuthRegisterInteractor,
        scope=Scope.REQUEST,
    )
    auth_login_interactor = provide(
        AuthLoginInteractor,
        scope=Scope.REQUEST,
    )
    auth_logout_interactor = provide(
        AuthLogoutInteractor,
        scope=Scope.REQUEST,
    )
    auth_refresh_interactor = provide(
        AuthRefreshInteractor,
        scope=Scope.REQUEST,
    )
    auth_forgot_password_interactor = provide(
        AuthForgotPasswordInteractor,
        scope=Scope.REQUEST,
    )
    auth_reset_password_interactor = provide(
        AuthResetPasswordInteractor,
        scope=Scope.REQUEST,
    )
    auth_change_password_interactor = provide(
        AuthChangePasswordInteractor,
        scope=Scope.REQUEST,
    )
    auth_me_interactor = provide(
        AuthMeInteractor,
        scope=Scope.REQUEST,
    )
    redis_service = provide(
        RedisService,
        scope=Scope.REQUEST,
    )
    user_service = provide(
        UserService,
        scope=Scope.REQUEST,
    )
    user_cache_service = provide(
        UserCacheService,
        scope=Scope.REQUEST,
    )
    auth_cache_service = provide(
        AuthCacheService,
        scope=Scope.REQUEST,
    )
    profile_service = provide(
        ProfileService,
        scope=Scope.REQUEST,
    )
    profile_cache_service = provide(
        ProfileCacheService,
        scope=Scope.REQUEST,
    )
    category_service = provide(
        CategoryService,
        scope=Scope.REQUEST,
    )
    category_cache_service = provide(
        CategoryCacheService,
        scope=Scope.REQUEST,
    )
    product_service = provide(
        ProductService,
        scope=Scope.REQUEST,
    )
    product_cache_service = provide(
        ProductCacheService,
        scope=Scope.REQUEST,
    )
    user_repository = provide(
        UserRepository,
        scope=Scope.REQUEST,
    )
    refresh_token_repository = provide(
        RefreshTokenRepository,
        scope=Scope.REQUEST,
    )
    admin_audit_log_repository = provide(
        AdminAuditLogRepository,
        scope=Scope.REQUEST,
    )
    address_repository = provide(
        AddressRepository,
        scope=Scope.REQUEST,
    )
    order_repository = provide(
        OrderRepository,
        scope=Scope.REQUEST,
    )
    order_item_repository = provide(
        OrderItemRepository,
        scope=Scope.REQUEST,
    )
    payment_repository = provide(
        PaymentRepository,
        scope=Scope.REQUEST,
    )
    payment_webhook_log_repository = provide(
        PaymentWebhookLogRepository,
        scope=Scope.REQUEST,
    )
    notification_repository = provide(
        NotificationRepository,
        scope=Scope.REQUEST,
    )
    notification_log_repository = provide(
        NotificationLogRepository,
        scope=Scope.REQUEST,
    )
    refund_repository = provide(
        RefundRepository,
        scope=Scope.REQUEST,
    )
    pickup_point_repository = provide(
        PickupPointRepository,
        scope=Scope.REQUEST,
    )
    product_repository = provide(
        ProductRepository,
        scope=Scope.REQUEST,
    )
    product_availability_log_repository = provide(
        ProductAvailabilityLogRepository,
        scope=Scope.REQUEST,
    )
    product_image_repository = provide(
        ProductImageRepository,
        scope=Scope.REQUEST,
    )
    stock_movement_repository = provide(
        StockMovementRepository,
        scope=Scope.REQUEST,
    )
    cart_repository = provide(
        CartRepository,
        scope=Scope.REQUEST,
    )
    cart_item_repository = provide(
        CartItemRepository,
        scope=Scope.REQUEST,
    )
    promo_code_repository = provide(
        PromoCodeRepository,
        scope=Scope.REQUEST,
    )
    promo_code_usage_repository = provide(
        PromoCodeUsageRepository,
        scope=Scope.REQUEST,
    )
    category_repository = provide(
        CategoryRepository,
        scope=Scope.REQUEST,
    )
    delivery_settings_repository = provide(
        DeliverySettingsRepository,
        scope=Scope.REQUEST,
    )
    delivery_time_slot_repository = provide(
        DeliveryTimeSlotRepository,
        scope=Scope.REQUEST,
    )
    delivery_zone_repository = provide(
        DeliveryZoneRepository,
        scope=Scope.REQUEST,
    )
    discount_repository = provide(
        DiscountRepository,
        scope=Scope.REQUEST,
    )
    favorite_repository = provide(
        FavoriteRepository,
        scope=Scope.REQUEST,
    )
    upload_repository = provide(
        UploadRepository,
        scope=Scope.REQUEST,
    )
    cart_service = provide(
        CartService,
        scope=Scope.REQUEST,
    )
    cart_calculator_service = provide(
        CartCalculatorService,
        scope=Scope.REQUEST,
    )
    stock_service = provide(
        StockService,
        scope=Scope.REQUEST,
    )
    stock_movement_service = provide(
        StockMovementService,
        scope=Scope.REQUEST,
    )
    promo_code_service = provide(
        PromoCodeService,
        scope=Scope.REQUEST,
    )
    order_service = provide(
        OrderService,
        scope=Scope.REQUEST,
    )
    order_cache_service = provide(
        OrderCacheService,
        scope=Scope.REQUEST,
    )
    payment_cache_service = provide(
        PaymentCacheService,
        scope=Scope.REQUEST,
    )
    payment_service = provide(
        PaymentService,
        scope=Scope.REQUEST,
    )
    payment_provider_service = provide(
        PaymentProviderService,
        scope=Scope.REQUEST,
    )
    payment_webhook_service = provide(
        PaymentWebhookService,
        scope=Scope.REQUEST,
    )
    delivery_service = provide(
        DeliveryService,
        scope=Scope.REQUEST,
    )
    delivery_zone_service = provide(
        DeliveryZoneService,
        scope=Scope.REQUEST,
    )
    delivery_time_slot_service = provide(
        DeliveryTimeSlotService,
        scope=Scope.REQUEST,
    )
    delivery_cache_service = provide(
        DeliveryCacheService,
        scope=Scope.REQUEST,
    )
    discount_service = provide(
        DiscountService,
        scope=Scope.REQUEST,
    )
    discount_cache_service = provide(
        DiscountCacheService,
        scope=Scope.REQUEST,
    )
    favorite_service = provide(
        FavoriteService,
        scope=Scope.REQUEST,
    )
    favorite_cache_service = provide(
        FavoriteCacheService,
        scope=Scope.REQUEST,
    )
    upload_service = provide(
        UploadService,
        scope=Scope.REQUEST,
    )
    upload_cache_service = provide(
        UploadCacheService,
        scope=Scope.REQUEST,
    )
    one_c_integration_service = provide(
        OneCIntegrationService,
        scope=Scope.REQUEST,
    )
    cart_cache_service = provide(
        CartCacheService,
        scope=Scope.REQUEST,
    )
    email_service = provide(
        EmailService,
        scope=Scope.REQUEST,
    )
    telegram_service = provide(
        TelegramNotificationService,
        scope=Scope.REQUEST,
    )
    notification_service = provide(
        NotificationService,
        scope=Scope.REQUEST,
    )
    notification_cache_service = provide(
        NotificationCacheService,
        scope=Scope.REQUEST,
    )
    admin_auth_service = provide(
        AdminAuthService,
        scope=Scope.REQUEST,
    )
    admin_auth_cache_service = provide(
        AdminAuthCacheService,
        scope=Scope.REQUEST,
    )
    admin_dashboard_service = provide(
        AdminDashboardService,
        scope=Scope.REQUEST,
    )
    admin_dashboard_cache_service = provide(
        AdminDashboardCacheService,
        scope=Scope.REQUEST,
    )
    admin_product_service = provide(
        AdminProductService,
        scope=Scope.REQUEST,
    )
    admin_product_cache_service = provide(
        AdminProductCacheService,
        scope=Scope.REQUEST,
    )
    jwt_service = provide(
        JwtService,
        scope=Scope.REQUEST,
    )
    jwt_blacklist_service = provide(
        JwtBlacklistService,
        scope=Scope.REQUEST,
    )
    rate_limit_service = provide(
        RateLimitService,
        scope=Scope.REQUEST,
    )
    audit_log_service = provide(
        AuditLogService,
        scope=Scope.REQUEST,
    )
    permission_service = provide(
        PermissionService,
        scope=Scope.REQUEST,
    )

    @provide(scope=Scope.REQUEST)
    def provide_storage_service(self, config: Settings) -> StorageService:
        return StorageService(media_settings=config.media)


class SessionProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_session_maker(self) -> async_sessionmaker[AsyncSession]:
        return db_helper.session_factory

    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> AsyncIterable[AsyncSession]:
        async with session_maker() as session:
            yield session


class RedisProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_redis(
        self,
        config: Settings,
    ) -> aioredis.Redis:
        url = config.redis.url
        return aioredis.from_url(url)


def setup_di() -> AsyncContainer:
    return make_async_container(
        AppProvider(),
        SessionProvider(),
        RedisProvider(),
        context={Settings: settings},
    )
