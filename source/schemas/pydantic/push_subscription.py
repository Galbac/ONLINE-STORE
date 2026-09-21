from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(..., description="Публичный ключ клиента P-256 (base64url)")
    auth: str = Field(..., description="Аутентификационный секрет клиента (base64url)")


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(..., description="Уникальный URL эндпоинта Web Push браузера")
    keys: PushSubscriptionKeys = Field(..., description="Ключи шифрования подписки")
    user_agent: str | None = Field(default=None, description="Строка User-Agent браузера")


class PushSubscriptionResponse(BaseModel):
    id: int
    endpoint: str
    is_active: bool
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class VapidPublicKeyResponse(BaseModel):
    public_key: str = Field(..., description="Открытый ключ VAPID сервера для регистрации в PushManager")


class SendPushNotificationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Заголовок уведомления")
    body: str = Field(..., min_length=1, description="Текст сообщения")
    url: str | None = Field(default="/", description="URL перехода при нажатии на уведомление")
    icon: str | None = Field(default="/icons/icon-192x192.png", description="URL иконки уведомления")
    badge: str | None = Field(default="/icons/badge-72x72.png", description="URL бейджа в статус-баре")
    tag: str | None = Field(default=None, description="Тег группировки уведомлений")


class PushResultResponse(BaseModel):
    success: bool
    sent_count: int
    failed_count: int
    message: str = "Уведомления успешно обработаны"
