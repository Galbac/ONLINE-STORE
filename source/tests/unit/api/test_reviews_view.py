from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.reviews import (
    create_product_review,
    get_admin_reviews,
    get_product_reviews,
    moderate_review,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.schemas.pydantic.review import (
    ReviewCreateRequest,
    ReviewListResponse,
    ReviewModerateRequest,
    ReviewResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=1, name="Иван Иванов", role=UserRole.CUSTOMER, is_active=True)


@pytest.fixture
def admin_user():
    return User(id=2, name="Администратор", role=UserRole.ADMIN, is_active=True)


@pytest.fixture
def fake_review_response():
    now = datetime.now(UTC)
    return ReviewResponse(
        id=10,
        product_id=5,
        user_id=1,
        user_name="Иван И.",
        rating=5,
        text="Отличный товар!",
        pros="Свежий",
        cons=None,
        image_url=None,
        is_approved=True,
        created_date=now,
    )


# ---------------------------------------------------------
# GET /products/{product_id}/reviews
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_product_reviews_success(fake_review_response):
    service = AsyncMock()
    service.get_product_reviews.return_value = ReviewListResponse(
        items=[fake_review_response],
        total=1,
        average_rating=5.0,
    )

    response = await unwrap(get_product_reviews)(
        product_id=5,
        session=AsyncMock(),
        review_repository=AsyncMock(),
        review_service=service,
    )

    assert response.total == 1
    assert response.items[0].user_name == "Иван И."


# ---------------------------------------------------------
# POST /products/{product_id}/reviews
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_create_product_review_success(active_user, fake_review_response):
    product_repo = AsyncMock()
    product_repo.get_by_id.return_value = SimpleNamespace(id=5, name="Яблоки")

    service = AsyncMock()
    service.create_review.return_value = fake_review_response

    body = ReviewCreateRequest(
        rating=5,
        text="Отличный товар!",
        pros="Свежий",
    )

    response = await unwrap(create_product_review)(
        product_id=5,
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        review_repository=AsyncMock(),
        product_repository=product_repo,
        review_service=service,
        commiter=AsyncMock(),
    )

    assert response.id == 10
    assert response.rating == 5


@pytest.mark.asyncio
async def test_create_product_review_product_not_found(active_user):
    product_repo = AsyncMock()
    product_repo.get_by_id.return_value = None

    body = ReviewCreateRequest(rating=5, text="Тест")
    with pytest.raises(HTTPException) as exc:
        await unwrap(create_product_review)(
            product_id=999,
            body=body,
            current_user=active_user,
            session=AsyncMock(),
            review_repository=AsyncMock(),
            product_repository=product_repo,
            review_service=AsyncMock(),
            commiter=AsyncMock(),
        )
    assert exc.value.status_code == 404
    assert "не найден" in exc.value.detail.lower()


# ---------------------------------------------------------
# GET /admin/reviews
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_admin_reviews_success(admin_user, fake_review_response):
    service = AsyncMock()
    service.get_all_reviews.return_value = ReviewListResponse(
        items=[fake_review_response],
        total=1,
        average_rating=5.0,
    )

    response = await unwrap(get_admin_reviews)(
        is_approved=None,
        current_user=admin_user,
        session=AsyncMock(),
        review_repository=AsyncMock(),
        review_service=service,
    )

    assert response.total == 1
    assert response.items[0].id == 10


# ---------------------------------------------------------
# PATCH /admin/reviews/{review_id}/moderate
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_moderate_review_success(admin_user, fake_review_response):
    service = AsyncMock()
    service.moderate_review.return_value = fake_review_response

    body = ReviewModerateRequest(is_approved=True)
    response = await unwrap(moderate_review)(
        review_id=10,
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        review_repository=AsyncMock(),
        review_service=service,
        commiter=AsyncMock(),
    )

    assert response.id == 10
    assert response.is_approved is True


@pytest.mark.asyncio
async def test_moderate_review_not_found(admin_user):
    service = AsyncMock()
    service.moderate_review.return_value = None

    body = ReviewModerateRequest(is_approved=False)
    with pytest.raises(HTTPException) as exc:
        await unwrap(moderate_review)(
            review_id=999,
            body=body,
            current_user=admin_user,
            session=AsyncMock(),
            review_repository=AsyncMock(),
            review_service=service,
            commiter=AsyncMock(),
        )
    assert exc.value.status_code == 404
