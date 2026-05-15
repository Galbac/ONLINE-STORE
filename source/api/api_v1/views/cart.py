from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.db.models.user import User
from source.errors.auth import InactiveUserError
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.cart import CartResponse
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["cart"])


@router.get(
    "/cart",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_cart(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> CartResponse:
    try:
        return await cart_service.get_current_cart(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            cart_calculator_service=cart_calculator_service,
            user=current_user,
        )
    except InactiveUserError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или удалён",
        ) from error
