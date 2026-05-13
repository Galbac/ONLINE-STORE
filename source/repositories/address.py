from datetime import datetime

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.address import Address
from source.schemas.pydantic.profile import (
    AddressCreateRequest,
    AddressResponse,
    AddressUpdateRequest,
    ProfileAddressShortResponse,
)


class AddressRepository:
    async def get_default_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> ProfileAddressShortResponse | None:
        result = await session.execute(
            select(Address)
            .where(
                Address.user_id == user_id,
                Address.is_default.is_(True),
                Address.is_deleted.is_(False),
            )
            .order_by(desc(Address.created_date))
            .limit(1),
        )
        address = result.scalar_one_or_none()
        if address is None:
            return None
        return ProfileAddressShortResponse(
            id=address.id,
            city=address.city,
            street=address.street,
            house=address.house,
            apartment=address.apartment,
        )

    async def count_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        include_deleted: bool = False,
    ) -> int:
        statement = select(func.count(Address.id)).where(Address.user_id == user_id)
        if not include_deleted:
            statement = statement.where(Address.is_deleted.is_(False))
        result = await session.execute(statement)
        return int(result.scalar_one())

    async def get_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AddressResponse]:
        statement = select(Address).where(Address.user_id == user_id)
        if not include_deleted:
            statement = statement.where(Address.is_deleted.is_(False))
        statement = (
            statement.order_by(desc(Address.is_default), desc(Address.created_date))
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(statement)
        return [
            self._build_address_response(address)
            for address in result.scalars().all()
        ]

    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        address_id: int,
    ) -> Address | None:
        result = await session.execute(select(Address).where(Address.id == address_id))
        return result.scalar_one_or_none()

    async def unset_default_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> None:
        await session.execute(
            update(Address)
            .where(
                Address.user_id == user_id,
                Address.is_default.is_(True),
                Address.is_deleted.is_(False),
            )
            .values(is_default=False),
        )

    async def create(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        data: AddressCreateRequest,
        is_default: bool,
    ) -> AddressResponse:
        address = Address(
            user_id=user_id,
            title=data.title,
            city=data.city,
            street=data.street,
            house=data.house,
            building=data.building,
            apartment=data.apartment,
            entrance=data.entrance,
            floor=data.floor,
            intercom=data.intercom,
            comment=data.comment,
            is_default=is_default,
            is_deleted=False,
        )
        session.add(address)
        await session.flush()
        await session.refresh(address)
        return self._build_address_response(address)

    async def update(
        self,
        *,
        session: AsyncSession,
        address: Address,
        data: AddressUpdateRequest,
    ) -> AddressResponse:
        update_data = data.model_dump(exclude_unset=True)
        for field_name, value in update_data.items():
            setattr(address, field_name, value)

        session.add(address)
        await session.flush()
        await session.refresh(address)
        return self._build_address_response(address)

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        address: Address,
    ) -> None:
        now = datetime.now(settings.tz)
        address.is_deleted = True
        address.deleted_at = now
        address.is_default = False
        address.updated_date = now
        session.add(address)
        await session.flush()

    async def get_first_active_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        exclude_address_id: int | None = None,
    ) -> Address | None:
        statement = select(Address).where(
            Address.user_id == user_id,
            Address.is_deleted.is_(False),
        )
        if exclude_address_id is not None:
            statement = statement.where(Address.id != exclude_address_id)
        statement = statement.order_by(desc(Address.created_date)).limit(1)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def set_default(
        self,
        *,
        session: AsyncSession,
        address: Address,
    ) -> None:
        address.is_default = True
        address.updated_date = datetime.now(settings.tz)
        session.add(address)
        await session.flush()

    def _build_address_response(self, address: Address) -> AddressResponse:
        return AddressResponse(
            id=address.id,
            title=address.title,
            city=address.city,
            street=address.street,
            house=address.house,
            building=address.building,
            apartment=address.apartment,
            entrance=address.entrance,
            floor=address.floor,
            intercom=address.intercom,
            comment=address.comment,
            is_default=address.is_default,
            created_at=address.created_date,
            updated_at=address.updated_date,
        )
