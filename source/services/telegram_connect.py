import secrets
from source.config.settings import settings
from source.db.models.user import User
from source.schemas.pydantic.telegram import TelegramConnectResponse, TelegramStatusResponse
from source.services.redis import RedisService


class TelegramConnectService:
    async def create_connect_token(
        self,
        *,
        redis_service: RedisService,
        user: User,
    ) -> TelegramConnectResponse:
        if user.telegram_chat_id:
            return TelegramConnectResponse(
                connect_url="",
                token="",
                expires_in_seconds=0,
                is_connected=True,
            )

        token = secrets.token_urlsafe(16)
        ttl = 600
        await redis_service.set(f"tg_connect:{token}", str(user.id), ttl_seconds=ttl)

        bot_name = getattr(settings.telegram, "bot_username", "GroceryStoreShopBot")
        url = f"https://t.me/{bot_name}?start={token}"

        return TelegramConnectResponse(
            connect_url=url,
            token=token,
            expires_in_seconds=ttl,
            is_connected=False,
        )

    async def get_status(self, *, user: User) -> TelegramStatusResponse:
        return TelegramStatusResponse(
            is_connected=bool(user.telegram_chat_id),
            telegram_chat_id=user.telegram_chat_id,
        )
