from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.banners import (
    create_admin_banner,
    delete_admin_banner,
    get_active_banners,
    get_admin_banners,
    update_admin_banner,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.schemas.pydantic.banner import (
    BannerCreateRequest,
    BannerListResponse,
    BannerResponse,
    BannerUpdateRequest,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def admin_user():
    return User(id=1, name="Администратор", role=UserRole.ADMIN, is_active=True)


@pytest.fixture
def fake_banner():
    return BannerResponse(
        id=1,
        title="Скидки до 30% на овощи",
        image_url="https://media.example.com/banner1.jpg",
        link_url="/catalog?category=vegetables",
        position=1,
        is_active=True,
        created_date=datetime.now(UTC),
    )


# ---------------------------------------------------------
# GET /banners
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_active_banners_success(fake_banner):
    service = AsyncMock()
    service.get_active_banners.return_value = BannerListResponse(
        items=[fake_banner],
        total=1,
    )

    response = await unwrap(get_active_banners)(
        session=AsyncMock(),
        banner_repository=AsyncMock(),
        banner_service=service,
    )

    assert response.total == 1
    assert response.items[0].title == "Скидки до 30% на овощи"


# ---------------------------------------------------------
# GET /admin/banners
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_admin_banners_success(admin_user, fake_banner):
    service = AsyncMock()
    service.get_all_banners.return_value = BannerListResponse(
        items=[fake_banner],
        total=1,
    )

    response = await unwrap(get_admin_banners)(
        current_user=admin_user,
        session=AsyncMock(),
        banner_repository=AsyncMock(),
        banner_service=service,
    )

    assert response.total == 1
    assert response.items[0].id == 1


# ---------------------------------------------------------
# POST /admin/banners
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_create_admin_banner_success(admin_user, fake_banner):
    service = AsyncMock()
    service.create_banner.return_value = fake_banner
    commiter = AsyncMock()

    body = BannerCreateRequest(
        title="Скидки до 30% на овощи",
        image_url="https://media.example.com/banner1.jpg",
        link_url="/catalog?category=vegetables",
        position=1,
        is_active=True,
    )

    response = await unwrap(create_admin_banner)(
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        banner_repository=AsyncMock(),
        banner_service=service,
        commiter=commiter,
    )

    assert response.id == 1
    assert service.create_banner.called


# ---------------------------------------------------------
# PATCH /admin/banners/{banner_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_update_admin_banner_success(admin_user, fake_banner):
    service = AsyncMock()
    updated_banner = fake_banner.model_copy(update={"title": "Обновленный заголовок"})
    service.update_banner.return_value = updated_banner
    commiter = AsyncMock()

    body = BannerUpdateRequest(title="Обновленный заголовок")
    response = await unwrap(update_admin_banner)(
        banner_id=1,
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        banner_repository=AsyncMock(),
        banner_service=service,
        commiter=commiter,
    )

    assert response.title == "Обновленный заголовок"


@pytest.mark.asyncio
async def test_update_admin_banner_not_found(admin_user):
    service = AsyncMock()
    service.update_banner.return_value = None

    body = BannerUpdateRequest(title="Тест")
    with pytest.raises(HTTPException) as exc:
        await unwrap(update_admin_banner)(
            banner_id=999,
            body=body,
            current_user=admin_user,
            session=AsyncMock(),
            banner_repository=AsyncMock(),
            banner_service=service,
            commiter=AsyncMock(),
        )
    assert exc.value.status_code == 404
    assert "не найден" in exc.value.detail.lower()


# ---------------------------------------------------------
# DELETE /admin/banners/{banner_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_admin_banner_success(admin_user):
    service = AsyncMock()
    service.delete_banner.return_value = True
    commiter = AsyncMock()

    await unwrap(delete_admin_banner)(
        banner_id=1,
        current_user=admin_user,
        session=AsyncMock(),
        banner_repository=AsyncMock(),
        banner_service=service,
        commiter=commiter,
    )
    assert service.delete_banner.called


@pytest.mark.asyncio
async def test_delete_admin_banner_not_found(admin_user):
    service = AsyncMock()
    service.delete_banner.return_value = False

    with pytest.raises(HTTPException) as exc:
        await unwrap(delete_admin_banner)(
            banner_id=999,
            current_user=admin_user,
            session=AsyncMock(),
            banner_repository=AsyncMock(),
            banner_service=service,
            commiter=AsyncMock(),
        )
    assert exc.value.status_code == 404
