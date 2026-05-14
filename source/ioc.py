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
from source.interactors.auth_register import AuthRegisterInteractor
from source.interactors.auth_reset_password import AuthResetPasswordInteractor
from source.repositories.address import AddressRepository
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.category import CategoryRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.product import ProductRepository
from source.repositories.user import UserRepository
from source.services.auth_cache import AuthCacheService
from source.services.auth import AuthService
from source.services.cart import CartService
from source.services.cart_cache import CartCacheService
from source.services.category import CategoryService
from source.services.category_cache import CategoryCacheService
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.profile import ProfileService
from source.services.profile_cache import ProfileCacheService
from source.services.redis import RedisService
from source.services.user import UserService
from source.services.user_cache import UserCacheService


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
    user_repository = provide(
        UserRepository,
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
    product_repository = provide(
        ProductRepository,
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
    category_repository = provide(
        CategoryRepository,
        scope=Scope.REQUEST,
    )
    cart_service = provide(
        CartService,
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
