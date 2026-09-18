from sqlalchemy.ext.asyncio import AsyncSession

from source.common.commiter import Commiter
from source.repositories.banner import BannerRepository
from source.schemas.pydantic.banner import (
    BannerCreateRequest,
    BannerListResponse,
    BannerResponse,
    BannerUpdateRequest,
)


class BannerService:
    async def get_active_banners(
        self,
        *,
        session: AsyncSession,
        banner_repository: BannerRepository,
    ) -> BannerListResponse:
        banners = await banner_repository.get_active_banners(session=session)
        return BannerListResponse(
            items=[BannerResponse.model_validate(b) for b in banners],
            total=len(banners),
        )

    async def get_all_banners(
        self,
        *,
        session: AsyncSession,
        banner_repository: BannerRepository,
    ) -> BannerListResponse:
        banners = await banner_repository.get_all(session=session)
        return BannerListResponse(
            items=[BannerResponse.model_validate(b) for b in banners],
            total=len(banners),
        )

    async def create_banner(
        self,
        *,
        session: AsyncSession,
        banner_repository: BannerRepository,
        commiter: Commiter,
        data: BannerCreateRequest,
    ) -> BannerResponse:
        banner = await banner_repository.create(
            session=session,
            **data.model_dump(),
        )
        await commiter.commit()
        return BannerResponse.model_validate(banner)

    async def update_banner(
        self,
        *,
        session: AsyncSession,
        banner_repository: BannerRepository,
        commiter: Commiter,
        banner_id: int,
        data: BannerUpdateRequest,
    ) -> BannerResponse | None:
        banner = await banner_repository.get_by_id(session=session, banner_id=banner_id)
        if banner is None:
            return None
        updated = await banner_repository.update(
            session=session,
            banner=banner,
            **data.model_dump(exclude_unset=True),
        )
        await commiter.commit()
        return BannerResponse.model_validate(updated)

    async def delete_banner(
        self,
        *,
        session: AsyncSession,
        banner_repository: BannerRepository,
        commiter: Commiter,
        banner_id: int,
    ) -> bool:
        banner = await banner_repository.get_by_id(session=session, banner_id=banner_id)
        if banner is None:
            return False
        await banner_repository.delete(session=session, banner=banner)
        await commiter.commit()
        return True
