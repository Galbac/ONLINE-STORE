from pydantic import BaseModel


class TelegramConnectResponse(BaseModel):
    connect_url: str
    token: str
    expires_in_seconds: int = 600
    is_connected: bool = False


class TelegramStatusResponse(BaseModel):
    is_connected: bool
    telegram_chat_id: str | None = None
