from sqlalchemy.ext.asyncio import AsyncSession

from source.common.commiter import Commiter
from source.db.models.user import User
from source.repositories.product import ProductRepository
from source.repositories.product_review import ProductReviewRepository
from source.schemas.pydantic.review import (
    ReviewCreateRequest,
    ReviewListResponse,
    ReviewResponse,
)


def mask_user_name(name: str | None) -> str:
    if not name or not name.strip():
        return "Покупатель"
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    first = parts[0]
    if len(first) > 2:
        return f"{first[:2]}***"
    return first


class ReviewService:
    async def get_product_reviews(
        self,
        *,
        session: AsyncSession,
        review_repository: ProductReviewRepository,
        product_id: int,
    ) -> ReviewListResponse:
        reviews = await review_repository.get_by_product(session=session, product_id=product_id)
        items = []
        total_rating = 0
        for r in reviews:
            user_name = mask_user_name(r.user.name) if r.user else "Покупатель"
            items.append(
                ReviewResponse(
                    id=r.id,
                    product_id=r.product_id,
                    user_id=r.user_id,
                    user_name=user_name,
                    rating=r.rating,
                    text=r.text,
                    pros=r.pros,
                    cons=r.cons,
                    image_url=r.image_url,
                    is_approved=r.is_approved,
                    created_date=r.created_date,
                )
            )
            total_rating += r.rating

        average = round(total_rating / len(items), 1) if items else 5.0
        return ReviewListResponse(items=items, total=len(items), average_rating=average)

    async def get_all_reviews(
        self,
        *,
        session: AsyncSession,
        review_repository: ProductReviewRepository,
        is_approved: bool | None = None,
    ) -> ReviewListResponse:
        reviews = await review_repository.get_all(session=session, is_approved=is_approved)
        items = []
        total_rating = 0
        for r in reviews:
            user_name = mask_user_name(r.user.name) if r.user else "Покупатель"
            items.append(
                ReviewResponse(
                    id=r.id,
                    product_id=r.product_id,
                    user_id=r.user_id,
                    user_name=user_name,
                    rating=r.rating,
                    text=r.text,
                    pros=r.pros,
                    cons=r.cons,
                    image_url=r.image_url,
                    is_approved=r.is_approved,
                    created_date=r.created_date,
                )
            )
            total_rating += r.rating

        average = round(total_rating / len(items), 1) if items else 5.0
        return ReviewListResponse(items=items, total=len(items), average_rating=average)

    async def create_review(
        self,
        *,
        session: AsyncSession,
        review_repository: ProductReviewRepository,
        product_repository: ProductRepository,
        commiter: Commiter,
        user: User,
        product_id: int,
        data: ReviewCreateRequest,
    ) -> ReviewResponse:
        review = await review_repository.create(
            session=session,
            product_id=product_id,
            user_id=user.id,
            rating=data.rating,
            text=data.text,
            pros=data.pros,
            cons=data.cons,
            image_url=data.image_url,
            is_approved=True,
        )
        await commiter.commit()
        return ReviewResponse(
            id=review.id,
            product_id=review.product_id,
            user_id=review.user_id,
            user_name=user.name,
            rating=review.rating,
            text=review.text,
            pros=review.pros,
            cons=review.cons,
            image_url=review.image_url,
            is_approved=review.is_approved,
            created_date=review.created_date,
        )

    async def moderate_review(
        self,
        *,
        session: AsyncSession,
        review_repository: ProductReviewRepository,
        commiter: Commiter,
        review_id: int,
        is_approved: bool,
    ) -> ReviewResponse | None:
        review = await review_repository.get_by_id(session=session, review_id=review_id)
        if review is None:
            return None
        updated = await review_repository.update(session=session, review=review, is_approved=is_approved)
        await commiter.commit()
        user_name = mask_user_name(updated.user.name) if updated.user else "Покупатель"
        return ReviewResponse(
            id=updated.id,
            product_id=updated.product_id,
            user_id=updated.user_id,
            user_name=user_name,
            rating=updated.rating,
            text=updated.text,
            pros=updated.pros,
            cons=updated.cons,
            image_url=updated.image_url,
            is_approved=updated.is_approved,
            created_date=updated.created_date,
        )
