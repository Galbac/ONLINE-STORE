from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, require_admin_or_manager
from source.common.commiter import Commiter
from source.db.models.user import User
from source.repositories.product import ProductRepository
from source.repositories.product_review import ProductReviewRepository
from source.schemas.pydantic.review import (
    ReviewCreateRequest,
    ReviewListResponse,
    ReviewModerateRequest,
    ReviewResponse,
)
from source.services.review import ReviewService

router = APIRouter(tags=["reviews"])


@router.get("/products/{product_id}/reviews", response_model=ReviewListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_product_reviews(
    product_id: int,
    session: FromDishka[AsyncSession] = None,
    review_repository: FromDishka[ProductReviewRepository] = None,
    review_service: FromDishka[ReviewService] = None,
) -> ReviewListResponse:
    return await review_service.get_product_reviews(
        session=session,
        review_repository=review_repository,
        product_id=product_id,
    )


@router.post("/products/{product_id}/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_product_review(
    product_id: int,
    body: ReviewCreateRequest,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    review_repository: FromDishka[ProductReviewRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    review_service: FromDishka[ReviewService] = None,
    commiter: FromDishka[Commiter] = None,
) -> ReviewResponse:
    product = await product_repository.get_by_id(session=session, product_id=product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    return await review_service.create_review(
        session=session,
        review_repository=review_repository,
        product_repository=product_repository,
        commiter=commiter,
        user=current_user,
        product_id=product_id,
        data=body,
    )


@router.get("/admin/reviews", response_model=ReviewListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_reviews(
    is_approved: bool | None = Query(default=None),
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    review_repository: FromDishka[ProductReviewRepository] = None,
    review_service: FromDishka[ReviewService] = None,
) -> ReviewListResponse:
    return await review_service.get_all_reviews(
        session=session,
        review_repository=review_repository,
        is_approved=is_approved,
    )


@router.patch("/admin/reviews/{review_id}/moderate", response_model=ReviewResponse, status_code=status.HTTP_200_OK)
@inject
async def moderate_review(
    review_id: int,
    body: ReviewModerateRequest,
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    review_repository: FromDishka[ProductReviewRepository] = None,
    review_service: FromDishka[ReviewService] = None,
    commiter: FromDishka[Commiter] = None,
) -> ReviewResponse:
    review = await review_service.moderate_review(
        session=session,
        review_repository=review_repository,
        commiter=commiter,
        review_id=review_id,
        is_approved=body.is_approved,
    )
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не найден")
    return review
