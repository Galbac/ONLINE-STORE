from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    CartInsufficientStockError,
    CartPieceQuantityMustBeIntegerError,
    CartProductNotFoundError,
    CartProductUnavailableError,
    CartQuantityBelowMinimumError,
    CartQuantityStepError,
    InactiveUserError,
)
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.cart import CartItemCreateRequest, CartResponse, MessageCartResponse
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.redis import RedisService
from source.services.stock import StockService

router = APIRouter(tags=["cart"])


@router.post(
    "/cart/items",
    response_model=MessageCartResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные данные корзины."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
        status.HTTP_404_NOT_FOUND: {"description": "Товар не найден."},
        status.HTTP_409_CONFLICT: {"description": "Товар недоступен или недостаточно остатка."},
    },
)
@inject
async def add_cart_item(
    body: CartItemCreateRequest = Body(),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    stock_service: FromDishka[StockService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.add_item(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            cart_calculator_service=cart_calculator_service,
            stock_service=stock_service,
            user=current_user,
            product_id=body.product_id,
            quantity=body.quantity,
        )
        await commiter.commit()
        return MessageCartResponse(message="Товар добавлен в корзину", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except CartProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except CartProductUnavailableError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Товар недоступен") from error
    except CartInsufficientStockError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Недостаточно товара на складе") from error
    except CartPieceQuantityMustBeIntegerError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для штучного товара количество должно быть целым числом",
        ) from error
    except CartQuantityStepError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество не соответствует шагу товара") from error
    except CartQuantityBelowMinimumError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество меньше минимального") from error


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
