from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    InvalidCredentialsError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.interactors.auth_login import AuthLoginInteractor
from source.interactors.auth_logout import AuthLogoutInteractor
from source.interactors.auth_register import AuthRegisterInteractor
from source.schemas.pydantic.auth import (
    AuthResponse,
    LogoutRequest,
    MessageResponse,
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


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Refresh token не найден.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Refresh token уже отозван.",
        },
    },
)
@inject
async def logout_user(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    auth_service: FromDishka[AuthService] = None,
    auth_logout_interactor: FromDishka[AuthLogoutInteractor] = None,
) -> MessageResponse:
    try:
        await auth_logout_interactor.execute(
            session=session,
            auth_service=auth_service,
            user=current_user,
            refresh_token=body.refresh_token,
        )
        await commiter.commit()
        return MessageResponse(message="Вы успешно вышли из аккаунта")
    except RefreshTokenNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token не найден",
        ) from error
    except RefreshTokenAlreadyRevokedError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token уже отозван",
        ) from error
