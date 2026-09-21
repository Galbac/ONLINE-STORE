from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user_optional, require_admin_or_manager
from source.common.commiter import Commiter
from source.db.models.user import User
from source.repositories.push_subscription import PushSubscriptionRepository
from source.schemas.pydantic.push_subscription import (
    PushResultResponse,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    SendPushNotificationRequest,
    VapidPublicKeyResponse,
)
from source.services.web_push import WebPushService

router = APIRouter(prefix="/notifications/push", tags=["push-notifications"])


@router.get(
    "/vapid-public-key",
    response_model=VapidPublicKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="Получить публичный VAPID ключ сервера",
)
@inject
async def get_vapid_public_key(
    web_push_service: FromDishka[WebPushService] = None,
) -> VapidPublicKeyResponse:
    return VapidPublicKeyResponse(public_key=web_push_service.get_public_key())


@router.post(
    "/subscribe",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Сохранить Web Push подписку браузера",
)
@inject
async def subscribe_push(
    body: PushSubscriptionCreate = Body(...),
    current_user: User | None = Depends(get_current_user_optional),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    push_subscription_repository: FromDishka[PushSubscriptionRepository] = None,
) -> PushSubscriptionResponse:
    try:
        subscription = await push_subscription_repository.save_or_update(
            session=session,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            user_id=current_user.id if current_user else None,
            user_agent=body.user_agent,
        )
        await commiter.commit()
        return PushSubscriptionResponse.model_validate(subscription)
    except Exception:
        await commiter.rollback()
        raise


@router.post(
    "/unsubscribe",
    status_code=status.HTTP_200_OK,
    summary="Отписаться от Web Push уведомлений",
)
@inject
async def unsubscribe_push(
    body: dict = Body(...),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    push_subscription_repository: FromDishka[PushSubscriptionRepository] = None,
) -> dict:
    endpoint = body.get("endpoint")
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="endpoint обязателен для отписки",
        )
    try:
        await push_subscription_repository.deactivate(session=session, endpoint=endpoint)
        await commiter.commit()
        return {"success": True, "message": "Подписка успешно деактивирована"}
    except Exception:
        await commiter.rollback()
        raise


@router.post(
    "/test",
    response_model=PushResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Отправить тестовое Web Push уведомление",
)
@inject
async def send_test_push(
    body: SendPushNotificationRequest = Body(...),
    current_user: User | None = Depends(get_current_user_optional),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    push_subscription_repository: FromDishka[PushSubscriptionRepository] = None,
    web_push_service: FromDishka[WebPushService] = None,
) -> PushResultResponse:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Авторизуйтесь для отправки тестового уведомления",
        )

    try:
        sent = await web_push_service.send_to_user(
            session=session,
            push_subscription_repository=push_subscription_repository,
            user_id=current_user.id,
            title=body.title,
            body=body.body,
            url=body.url or "/",
            icon=body.icon,
            badge=body.badge,
            tag=body.tag,
        )
        await commiter.commit()
        return PushResultResponse(
            success=sent > 0,
            sent_count=sent,
            failed_count=0 if sent > 0 else 1,
            message="Тестовое уведомление отправлено" if sent > 0 else "Нет активных подписок для пользователя",
        )
    except Exception:
        await commiter.rollback()
        raise


@router.post(
    "/broadcast",
    response_model=PushResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Массовая рассылка пушей (только для админов/менеджеров)",
)
@inject
async def broadcast_push(
    body: SendPushNotificationRequest = Body(...),
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    push_subscription_repository: FromDishka[PushSubscriptionRepository] = None,
    web_push_service: FromDishka[WebPushService] = None,
) -> PushResultResponse:
    try:
        sent, failed = await web_push_service.broadcast(
            session=session,
            push_subscription_repository=push_subscription_repository,
            title=body.title,
            body=body.body,
            url=body.url or "/",
            icon=body.icon,
            badge=body.badge,
            tag=body.tag,
        )
        await commiter.commit()
        return PushResultResponse(
            success=True,
            sent_count=sent,
            failed_count=failed,
            message=f"Разослано: {sent}, ошибок: {failed}",
        )
    except Exception:
        await commiter.rollback()
        raise
