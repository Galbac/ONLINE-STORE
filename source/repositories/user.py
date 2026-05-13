from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.user import User


class UserRepository:
    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
