from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.push_subscription import PushSubscription


class PushSubscriptionRepository:
    async def save_or_update(
        self,
        *,
        session: AsyncSession,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_id: int | None = None,
        user_agent: str | None = None,
    ) -> PushSubscription:
        statement = (
            insert(PushSubscription)
            .values(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_id=user_id,
                user_agent=user_agent,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=[PushSubscription.endpoint],
                set_={
                    "p256dh": p256dh,
                    "auth": auth,
                    "is_active": True,
                    "user_id": (
                        user_id if user_id is not None else PushSubscription.user_id
                    ),
                    "user_agent": (
                        user_agent
                        if user_agent is not None
                        else PushSubscription.user_agent
                    ),
                },
            )
            .returning(PushSubscription)
        )
        result = await session.execute(
            statement.execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def get_by_endpoint(
        self,
        *,
        session: AsyncSession,
        endpoint: str,
    ) -> PushSubscription | None:
        result = await session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        return result.scalar_one_or_none()

    async def get_active_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> list[PushSubscription]:
        result = await session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_all_active(
        self,
        *,
        session: AsyncSession,
    ) -> list[PushSubscription]:
        result = await session.execute(
            select(PushSubscription).where(PushSubscription.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def deactivate(
        self,
        *,
        session: AsyncSession,
        endpoint: str,
    ) -> None:
        await session.execute(
            update(PushSubscription)
            .where(PushSubscription.endpoint == endpoint)
            .values(is_active=False)
        )
        await session.flush()

    async def delete_by_endpoint(
        self,
        *,
        session: AsyncSession,
        endpoint: str,
    ) -> None:
        result = await session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        subscription = result.scalar_one_or_none()
        if subscription is not None:
            await session.delete(subscription)
            await session.flush()
