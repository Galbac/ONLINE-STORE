from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import require_permission
from source.common.commiter import Commiter
from source.db.models.user import User
from source.repositories.banner import BannerRepository
from source.schemas.pydantic.banner import (
    BannerCreateRequest,
    BannerListResponse,
    BannerResponse,
    BannerUpdateRequest,
)
from source.services.banner import BannerService

router = APIRouter(tags=["banners"])


@router.get("/banners", response_model=BannerListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_active_banners(
    session: FromDishka[AsyncSession] = None,
    banner_repository: FromDishka[BannerRepository] = None,
    banner_service: FromDishka[BannerService] = None,
) -> BannerListResponse:
    return await banner_service.get_active_banners(
        session=session,
        banner_repository=banner_repository,
    )


@router.get("/admin/banners", response_model=BannerListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_banners(
    current_user: User = Depends(require_permission("admin:settings:read")),
    session: FromDishka[AsyncSession] = None,
    banner_repository: FromDishka[BannerRepository] = None,
    banner_service: FromDishka[BannerService] = None,
) -> BannerListResponse:
    return await banner_service.get_all_banners(
        session=session,
        banner_repository=banner_repository,
    )


@router.post("/admin/banners", response_model=BannerResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_admin_banner(
    body: BannerCreateRequest,
    current_user: User = Depends(require_permission("admin:settings:update")),
    session: FromDishka[AsyncSession] = None,
    banner_repository: FromDishka[BannerRepository] = None,
    banner_service: FromDishka[BannerService] = None,
    commiter: FromDishka[Commiter] = None,
) -> BannerResponse:
    return await banner_service.create_banner(
        session=session,
        banner_repository=banner_repository,
        commiter=commiter,
        data=body,
    )


@router.patch("/admin/banners/{banner_id}", response_model=BannerResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_banner(
    banner_id: int,
    body: BannerUpdateRequest,
    current_user: User = Depends(require_permission("admin:settings:update")),
    session: FromDishka[AsyncSession] = None,
    banner_repository: FromDishka[BannerRepository] = None,
    banner_service: FromDishka[BannerService] = None,
    commiter: FromDishka[Commiter] = None,
) -> BannerResponse:
    banner = await banner_service.update_banner(
        session=session,
        banner_repository=banner_repository,
        commiter=commiter,
        banner_id=banner_id,
        data=body,
    )
    if banner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Баннер не найден")
    return banner


@router.delete("/admin/banners/{banner_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_admin_banner(
    banner_id: int,
    current_user: User = Depends(require_permission("admin:settings:update")),
    session: FromDishka[AsyncSession] = None,
    banner_repository: FromDishka[BannerRepository] = None,
    banner_service: FromDishka[BannerService] = None,
    commiter: FromDishka[Commiter] = None,
) -> None:
    deleted = await banner_service.delete_banner(
        session=session,
        banner_repository=banner_repository,
        commiter=commiter,
        banner_id=banner_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Баннер не найден")
