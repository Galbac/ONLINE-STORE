from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, require_admin_or_manager, require_permission
from source.common.commiter import Commiter
from source.config.settings import settings
from source.db.models.user import User
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.notification import (
    NotificationAccessDeniedError,
    NotificationEmailDisabledError,
    NotificationNotFoundError,
    NotificationSendError,
    NotificationTelegramChatIdMissingError,
    NotificationTelegramDisabledError,
)
from source.errors.settings import EmptyNotificationSettingsUpdateError
from source.repositories.admin_audit_log import AdminAuditLogRepository
from source.repositories.notification import NotificationLogRepository, NotificationRepository, NotificationSettingsRepository
from source.schemas.pydantic.notifications import (
    AdminNotificationSettingsResponse,
    AdminNotificationSettingsUpdateRequest,
    MessageResponse,
    NotificationListResponse,
    NotificationQueryParams,
    NotificationResponse,
    TestEmailRequest,
    TestTelegramRequest,
)
from source.services.notification_cache import NotificationCacheService
from source.services.notification_settings_cache import NotificationSettingsCacheService
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_notification import AdminNotificationService
from source.services.notifications import EmailService, NotificationService, TelegramNotificationService
from source.services.redis import RedisService

router = APIRouter(tags=["notifications"])


@router.get(
    "/admin/notifications/settings",
    response_model=AdminNotificationSettingsResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_admin_notification_settings(
    current_user: User = Depends(require_permission("admin:notifications:read")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_notification_service: FromDishka[AdminNotificationService] = None,
    permission_service: FromDishka[PermissionService] = None,
    notification_settings_repository: FromDishka[NotificationSettingsRepository] = None,
    notification_settings_cache_service: FromDishka[NotificationSettingsCacheService] = None,
) -> AdminNotificationSettingsResponse:
    try:
        return await admin_notification_service.get_settings(
            session=session,
            redis_service=redis_service,
            user=current_user,
            commiter=commiter,
            permission_service=permission_service,
            notification_settings_repository=notification_settings_repository,
            notification_settings_cache_service=notification_settings_cache_service,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error


@router.patch(
    "/admin/notifications/settings",
    response_model=AdminNotificationSettingsResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def update_admin_notification_settings(
    request: Request,
    body: dict = Body(default_factory=dict),
    current_user: User = Depends(require_permission("admin:notifications:update")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_notification_service: FromDishka[AdminNotificationService] = None,
    permission_service: FromDishka[PermissionService] = None,
    notification_settings_repository: FromDishka[NotificationSettingsRepository] = None,
    notification_settings_cache_service: FromDishka[NotificationSettingsCacheService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminNotificationSettingsResponse:
    try:
        data = AdminNotificationSettingsUpdateRequest.model_validate(body)
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректные настройки уведомлений") from error

    try:
        return await admin_notification_service.update_settings(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=data,
            commiter=commiter,
            permission_service=permission_service,
            notification_settings_repository=notification_settings_repository,
            notification_settings_cache_service=notification_settings_cache_service,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )
    except EmptyNotificationSettingsUpdateError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля") from error
    except (AdminAuthAccessDeniedError, InactiveUserError) as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error


@router.get("/notifications", response_model=NotificationListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_notifications(
    current_user: User = Depends(get_current_user),
    unread_only: bool = Query(default=False),
    type_filter: str | None = Query(default=None, alias="type", max_length=50),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.notifications.default_limit, ge=1, le=settings.notifications.max_limit),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    notification_service: FromDishka[NotificationService] = None,
    notification_repository: FromDishka[NotificationRepository] = None,
    notification_cache_service: FromDishka[NotificationCacheService] = None,
) -> NotificationListResponse:
    try:
        return await notification_service.get_user_notifications(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=NotificationQueryParams(
                unread_only=unread_only,
                type=type_filter,
                page=page,
                limit=limit,
            ),
            notification_repository=notification_repository,
            notification_cache_service=notification_cache_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    notification_service: FromDishka[NotificationService] = None,
    notification_repository: FromDishka[NotificationRepository] = None,
    notification_cache_service: FromDishka[NotificationCacheService] = None,
) -> NotificationResponse:
    if notification_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный notification_id")
    try:
        response = await notification_service.mark_as_read(
            session=session,
            redis_service=redis_service,
            user=current_user,
            notification_id=notification_id,
            notification_repository=notification_repository,
            notification_cache_service=notification_cache_service,
        )
        await commiter.commit()
        return response
    except NotificationNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Уведомление не найдено") from error
    except NotificationAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Уведомление принадлежит другому пользователю") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except Exception:
        await commiter.rollback()
        raise


@router.post("/notifications/test-email", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@inject
async def send_test_email(
    body: TestEmailRequest = Body(...),
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    notification_service: FromDishka[NotificationService] = None,
    email_service: FromDishka[EmailService] = None,
    notification_log_repository: FromDishka[NotificationLogRepository] = None,
) -> MessageResponse:
    try:
        response = await notification_service.send_test_email(
            session=session,
            user=current_user,
            data=body,
            email_service=email_service,
            notification_log_repository=notification_log_repository,
        )
        await commiter.commit()
        return response
    except NotificationEmailDisabledError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Email-уведомления выключены") from error
    except NotificationSendError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка отправки email") from error
    except Exception:
        await commiter.rollback()
        raise


@router.post("/notifications/test-telegram", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@inject
async def send_test_telegram(
    body: TestTelegramRequest = Body(default_factory=TestTelegramRequest),
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    notification_service: FromDishka[NotificationService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    notification_log_repository: FromDishka[NotificationLogRepository] = None,
) -> MessageResponse:
    try:
        response = await notification_service.send_test_telegram(
            session=session,
            user=current_user,
            data=body,
            telegram_service=telegram_service,
            notification_log_repository=notification_log_repository,
        )
        await commiter.commit()
        return response
    except NotificationTelegramChatIdMissingError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chat_id не передан и не задан в ENV") from error
    except NotificationTelegramDisabledError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Telegram-уведомления выключены") from error
    except NotificationSendError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка отправки Telegram") from error
    except Exception:
        await commiter.rollback()
        raise
