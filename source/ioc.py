from collections.abc import AsyncIterable

from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from source.common.commiter import Commiter
from source.config.settings import Settings, settings
from source.db.db_helper import db_helper
from source.db.sa_commiter import SACommiter
from source.interactors.auth_forgot_password import AuthForgotPasswordInteractor
from source.interactors.auth_login import AuthLoginInteractor
from source.interactors.auth_logout import AuthLogoutInteractor
from source.interactors.auth_register import AuthRegisterInteractor
from source.services.auth import AuthService
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.redis import RedisService


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
    redis_service = provide(
        RedisService,
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
