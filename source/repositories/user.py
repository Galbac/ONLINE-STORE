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

    async def get_by_phone(
        self,
        *,
        session: AsyncSession,
        phone: str,
    ) -> User | None:
        result = await session.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def get_by_email(
        self,
        *,
        session: AsyncSession,
        email: str,
    ) -> User | None:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def update(
        self,
        *,
        session: AsyncSession,
        user: User,
    ) -> User:
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user
