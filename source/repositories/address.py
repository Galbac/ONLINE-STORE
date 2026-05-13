from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.address import Address
from source.schemas.pydantic.profile import AddressResponse, ProfileAddressShortResponse


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
