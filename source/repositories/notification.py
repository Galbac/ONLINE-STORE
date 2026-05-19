from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.notification import Notification, NotificationLog
from source.schemas.pydantic.notifications import NotificationQueryParams, NotificationResponse


class NotificationRepository:
    async def get_by_id(self, *, session: AsyncSession, notification_id: int) -> Notification | None:
        result = await session.execute(select(Notification).where(Notification.id == notification_id))
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        query: NotificationQueryParams,
    ) -> list[NotificationResponse]:
        statement = select(Notification).where(Notification.user_id == user_id)
        statement = self._apply_filters(statement, query=query)
        statement = statement.order_by(desc(Notification.created_date)).limit(query.limit).offset(query.offset)
        result = await session.execute(statement)
        return [self._build_response(notification) for notification in result.scalars().all()]

    async def count_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        query: NotificationQueryParams | None = None,
    ) -> int:
        statement = select(func.count(Notification.id)).where(Notification.user_id == user_id)
        statement = self._apply_filters(statement, query=query)
        result = await session.execute(statement)
        return int(result.scalar_one())

    async def count_unread_by_user_id(self, *, session: AsyncSession, user_id: int) -> int:
        result = await session.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            ),
        )
        return int(result.scalar_one())

    async def mark_as_read(self, *, session: AsyncSession, notification: Notification) -> Notification:
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(settings.tz)
            session.add(notification)
            await session.flush()
            await session.refresh(notification)
        return notification

    def _apply_filters(self, statement, *, query: NotificationQueryParams | None):
        if query is None:
            return statement
        if query.unread_only:
            statement = statement.where(Notification.is_read.is_(False))
        if query.type is not None:
            statement = statement.where(Notification.type == query.type)
        return statement

    def _build_response(self, notification: Notification) -> NotificationResponse:
        return NotificationResponse(
            id=notification.id,
            type=notification.type,
            title=notification.title,
            message=notification.message,
            is_read=notification.is_read,
            read_at=notification.read_at,
            created_at=notification.created_date,
        )


class NotificationLogRepository:
    async def create(self, *, session: AsyncSession, **data) -> NotificationLog:
        log = NotificationLog(**data)
        session.add(log)
        await session.flush()
        await session.refresh(log)
        return log
