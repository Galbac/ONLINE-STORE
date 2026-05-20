from datetime import datetime, time

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.user import User
from source.db.models.choises.enum import UserRole
from source.schemas.pydantic.admin_staff import AdminStaffListQueryParams
from source.schemas.pydantic.user import AdminUserListQueryParams

STAFF_ROLES = (
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.CONTENT_MANAGER,
    UserRole.PICKER,
    UserRole.COURIER,
)


class UserRepository:
    async def create(self, *, session: AsyncSession, **data) -> User:
        user = User(**data)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user

    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def count_customers(self, *, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(User.id)).where(
                User.role == UserRole.CUSTOMER,
                User.is_deleted.is_(False),
            ),
        )
        return int(result.scalar_one())

    async def admin_get_customers(
        self,
        *,
        session: AsyncSession,
        query: AdminUserListQueryParams,
    ) -> list[User]:
        statement = self._apply_admin_customer_filters(select(User), query=query)
        result = await session.execute(
            statement.order_by(desc(User.created_date)).limit(query.limit).offset(query.offset),
        )
        return list(result.scalars().all())

    async def admin_count_customers(
        self,
        *,
        session: AsyncSession,
        query: AdminUserListQueryParams,
    ) -> int:
        statement = self._apply_admin_customer_filters(select(User.id), query=query).subquery()
        result = await session.execute(select(func.count()).select_from(statement))
        return int(result.scalar_one())

    async def admin_get_staff_list(
        self,
        *,
        session: AsyncSession,
        query: AdminStaffListQueryParams,
    ) -> list[User]:
        statement = self._apply_admin_staff_filters(select(User), query=query)
        result = await session.execute(
            statement.order_by(desc(User.created_date)).limit(query.limit).offset(query.offset),
        )
        return list(result.scalars().all())

    async def admin_count_staff(
        self,
        *,
        session: AsyncSession,
        query: AdminStaffListQueryParams,
    ) -> int:
        statement = self._apply_admin_staff_filters(select(User.id), query=query).subquery()
        result = await session.execute(select(func.count()).select_from(statement))
        return int(result.scalar_one())

    async def count_active_admins(self, *, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.is_deleted.is_(False),
                User.is_blocked.is_(False),
            ),
        )
        return int(result.scalar_one())

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

    async def block(
        self,
        *,
        session: AsyncSession,
        user: User,
        blocked_at: datetime,
        blocked_by: int,
        block_reason: str,
    ) -> User:
        user.is_blocked = True
        user.blocked_at = blocked_at
        user.blocked_by = blocked_by
        user.block_reason = block_reason
        user.updated_date = blocked_at
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user

    async def unblock(
        self,
        *,
        session: AsyncSession,
        user: User,
        unblocked_at: datetime,
        unblocked_by: int,
        unblock_reason: str,
    ) -> User:
        user.is_blocked = False
        user.unblocked_at = unblocked_at
        user.unblocked_by = unblocked_by
        user.unblock_reason = unblock_reason
        user.updated_date = unblocked_at
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user

    def _apply_admin_customer_filters(self, statement, *, query: AdminUserListQueryParams):
        statement = statement.where(User.role == UserRole.CUSTOMER)
        if query.q is not None:
            search = f"%{query.q}%"
            statement = statement.where(
                or_(
                    User.name.ilike(search),
                    User.phone.ilike(search),
                    User.email.ilike(search),
                ),
            )
        if query.is_active is not None:
            statement = statement.where(User.is_active.is_(query.is_active))
        if query.is_blocked is not None:
            statement = statement.where(User.is_blocked.is_(query.is_blocked))
        if query.is_deleted is not None:
            statement = statement.where(User.is_deleted.is_(query.is_deleted))
        else:
            statement = statement.where(User.is_deleted.is_(False))
        if query.date_from is not None:
            statement = statement.where(User.created_date >= datetime.combine(query.date_from, time.min))
        if query.date_to is not None:
            statement = statement.where(User.created_date <= datetime.combine(query.date_to, time.max))
        return statement

    def _apply_admin_staff_filters(self, statement, *, query: AdminStaffListQueryParams):
        statement = statement.where(User.role.in_(STAFF_ROLES))
        if query.q is not None:
            search = f"%{query.q}%"
            statement = statement.where(
                or_(
                    User.name.ilike(search),
                    User.phone.ilike(search),
                    User.email.ilike(search),
                ),
            )
        if query.role is not None:
            statement = statement.where(User.role == query.role)
        if query.is_active is not None:
            statement = statement.where(User.is_active.is_(query.is_active))
        if query.is_blocked is not None:
            statement = statement.where(User.is_blocked.is_(query.is_blocked))
        return statement
