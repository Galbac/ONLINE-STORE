from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.profile import ProfileOrderShortResponse


class OrderRepository:
    async def count_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        return 0

    async def get_recent_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        limit: int = 5,
    ) -> list[ProfileOrderShortResponse]:
        return []

    async def get_active_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> ProfileOrderShortResponse | None:
        return None

    async def has_active_orders_by_address_id(
        self,
        *,
        session: AsyncSession,
        address_id: int,
    ) -> bool:
        return False
