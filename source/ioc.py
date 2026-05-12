from collections.abc import AsyncIterable

from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from source.common.commiter import Commiter
from source.config.settings import Settings, settings
from source.db.db_helper import db_helper
from source.db.sa_commiter import SACommiter
from source.interactors.auth_register import AuthRegisterInteractor
from source.services.auth import AuthService


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


def setup_di() -> AsyncContainer:
    return make_async_container(
        AppProvider(),
        SessionProvider(),
        context={Settings: settings},
    )
