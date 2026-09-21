from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest

from source.db.models.choises.enum import UserRole
from source.db.models.product_review import ProductReview
from source.db.models.user import User
from source.services.review import ReviewService, mask_user_name


def test_mask_user_name_edge_cases():
    # ФИО -> Имя + Первая буква фамилии с точкой
    assert mask_user_name("Иван Иванов") == "Иван И."
    assert mask_user_name("Алексей Петрович Сидоров") == "Алексей П."

    # Одиночные имена длиннее 2 символов
    assert mask_user_name("Алексей") == "Ал***"
    assert mask_user_name("Ольга") == "Ол***"

    # Короткие имена
    assert mask_user_name("Ян") == "Ян"
    assert mask_user_name("Ли") == "Ли"

    # Пустые и None значения
    assert mask_user_name(None) == "Покупатель"
    assert mask_user_name("") == "Покупатель"
    assert mask_user_name("   ") == "Покупатель"


@pytest.mark.asyncio
async def test_review_service_masks_user_names():
    session = AsyncMock()
    repo = AsyncMock()

    user_1 = User(id=1, name="Сергей Смирнов", role=UserRole.CUSTOMER, is_active=True)
    user_2 = User(id=2, name="Екатерина", role=UserRole.CUSTOMER, is_active=True)

    r1 = ProductReview(
        id=1,
        product_id=5,
        user_id=1,
        rating=5,
        text="Отличное качество продуктов!",
        pros="Свежее",
        cons=None,
        is_approved=True,
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    r1.user = user_1

    r2 = ProductReview(
        id=2,
        product_id=5,
        user_id=2,
        rating=4,
        text="Быстрая доставка",
        pros=None,
        cons=None,
        is_approved=True,
        created_date=datetime.now(UTC),
        updated_date=datetime.now(UTC),
    )
    r2.user = user_2

    repo.get_by_product.return_value = [r1, r2]

    service = ReviewService()
    response = await service.get_product_reviews(
        session=session,
        review_repository=repo,
        product_id=5,
    )

    assert response.total == 2
    assert response.items[0].user_name == "Сергей С."
    assert response.items[1].user_name == "Ек***"
