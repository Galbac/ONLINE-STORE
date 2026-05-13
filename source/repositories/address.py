from sqlalchemy.ext.asyncio import AsyncSession

from source.schemas.pydantic.profile import ProfileAddressShortResponse


class AddressRepository:
    async def get_default_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> ProfileAddressShortResponse | None:
        return None

    async def count_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        return 0
