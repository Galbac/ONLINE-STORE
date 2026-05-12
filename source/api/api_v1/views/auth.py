from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    NewPasswordSameAsOldError,
    PasswordResetRateLimitExceededError,
    PasswordResetUserNotFoundError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.interactors.auth_forgot_password import AuthForgotPasswordInteractor
from source.interactors.auth_login import AuthLoginInteractor
from source.interactors.auth_logout import AuthLogoutInteractor
from source.interactors.auth_register import AuthRegisterInteractor
from source.interactors.auth_reset_password import AuthResetPasswordInteractor
from source.schemas.pydantic.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LogoutRequest,
    MessageResponse,
    RegisterAuthResponse,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from source.services.auth import AuthService
from source.services.notifications import EmailService, TelegramNotificationService
from source.services.redis import RedisService

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


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверный формат login.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Слишком много запросов на восстановление пароля.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: FromDishka[AsyncSession],
    auth_service: FromDishka[AuthService],
    redis_service: FromDishka[RedisService],
    email_service: FromDishka[EmailService],
    telegram_service: FromDishka[TelegramNotificationService],
    auth_forgot_password_interactor: FromDishka[AuthForgotPasswordInteractor],
) -> MessageResponse:
    try:
        return await auth_forgot_password_interactor.execute(
            session=session,
            auth_service=auth_service,
            redis_service=redis_service,
            email_service=email_service,
            telegram_service=telegram_service,
            data=body,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent"),
        )
    except PasswordResetRateLimitExceededError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много запросов на восстановление пароля",
        ) from error


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Пароли не совпадают, пароль слишком слабый или совпадает со старым.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Недействительный или истёкший токен восстановления.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или неактивен.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Пользователь не найден.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def reset_password(
    body: ResetPasswordRequest,
    session: FromDishka[AsyncSession],
    commiter: FromDishka[Commiter],
    auth_service: FromDishka[AuthService],
    redis_service: FromDishka[RedisService],
    auth_reset_password_interactor: FromDishka[AuthResetPasswordInteractor],
) -> MessageResponse:
    try:
        response = await auth_reset_password_interactor.execute(
            session=session,
            auth_service=auth_service,
            redis_service=redis_service,
            data=body,
        )
        await commiter.commit()
        return response
    except InvalidPasswordResetTokenError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший токен восстановления",
        ) from error
    except PasswordResetUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        ) from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или неактивен",
        ) from error
    except NewPasswordSameAsOldError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новый пароль совпадает со старым",
        ) from error
