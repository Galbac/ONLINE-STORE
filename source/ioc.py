from collections.abc import AsyncIterable

import redis.asyncio as aioredis
from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    from_context,
    make_async_container,
    provide,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from source.common.commiter import Commiter
from source.config.settings import Settings, settings
from source.db.db_helper import db_helper
from source.db.sa_commiter import SACommiter
from source.interactors.auth_init import AuthInitInteractor
from source.interactors.auth_init_data import AuthInitDataInteractor
from source.interactors.auth_send_code import AuthSendCodeInteractor
from source.interactors.auth_verify_code import AuthVerifyCodeInteractor
from source.interactors.admin.facade import AdminInteractor
from source.interactors.free_key import FreeKeyInteractor
from source.interactors.health import HealthInteractor
from source.interactors.link_email_send_code import LinkEmailSendCodeInteractor
from source.interactors.link_email_verify_code import LinkEmailVerifyCodeInteractor
from source.interactors.link_telegram import LinkTelegramInteractor
from source.interactors.me_profile import MeProfileInteractor
from source.interactors.notification_settings import NotificationSettingsInteractor
from source.interactors.order_cancel import OrderCancelInteractor
from source.interactors.order_create import OrderCreateInteractor
from source.interactors.order_payment_link import OrderPaymentLinkInteractor
from source.interactors.order_payment_status import OrderPaymentStatusInteractor
from source.interactors.order_history import OrderHistoryInteractor
from source.interactors.order_status import OrderStatusInteractor
from source.interactors.static_config import StaticConfigInteractor
from source.interactors.tariffs_list import TariffsListInteractor
from source.interactors.user_subscription import UserSubscriptionInteractor
from source.interactors.winback import WinbackInteractor
from source.services.payment_service import PaymentService
from source.services.referral_service import ReferralService


class AppProvider(Provider):
    config = from_context(provides=Settings, scope=Scope.APP)

    sa_commiter = provide(
        SACommiter,
        scope=Scope.REQUEST,
        provides=Commiter,
    )

class SessionProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_session_maker(self) -> async_sessionmaker[AsyncSession]:
        return db_helper.session_factory

    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> AsyncIterable[AsyncSession,]:
        async with session_maker() as session:
            yield session


class RedisProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_redis(
        self,
        config: Settings,
    ) -> aioredis.Redis:
        url = config.worker.celery_broker_url
        return aioredis.from_url(url)


def setup_di() -> AsyncContainer:
    return make_async_container(
        AppProvider(),
        SessionProvider(),
        RedisProvider(),
        context={Settings: settings},
    )
