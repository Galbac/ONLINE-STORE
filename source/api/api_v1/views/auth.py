from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.common.commiter import Commiter
from source.errors.auth import (
    InactiveUserError,
    InvalidCredentialsError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.interactors.auth_login import AuthLoginInteractor
from source.interactors.auth_register import AuthRegisterInteractor
from source.schemas.pydantic.auth import (
    AuthResponse,
    RegisterAuthResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from source.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterAuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные входные данные.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Пользователь с таким телефоном или email уже существует.",
        },
    },
)
@inject
async def register_user(
    body: UserRegisterRequest,
    session: FromDishka[AsyncSession],
    commiter: FromDishka[Commiter],
    auth_service: FromDishka[AuthService],
    auth_register_interactor: FromDishka[AuthRegisterInteractor],
) -> RegisterAuthResponse:
    try:
        response = await auth_register_interactor.execute(
            session=session,
            auth_service=auth_service,
            data=body,
        )
        await commiter.commit()
        return response
    except UserPhoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким телефоном уже существует",
        ) from error
    except UserEmailAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        ) from error


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные входные данные.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Неверный логин или пароль.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или неактивен.",
        },
    },
)
@inject
async def login_user(
    body: UserLoginRequest,
    session: FromDishka[AsyncSession],
    commiter: FromDishka[Commiter],
    auth_service: FromDishka[AuthService],
    auth_login_interactor: FromDishka[AuthLoginInteractor],
) -> AuthResponse:
    try:
        response = await auth_login_interactor.execute(
            session=session,
            auth_service=auth_service,
            data=body,
        )
        await commiter.commit()
        return response
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        ) from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или неактивен",
        ) from error
