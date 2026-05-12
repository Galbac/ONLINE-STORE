import pytest

from source.db.models.choises.enum import UserRole
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import InactiveUserError, InvalidCredentialsError
from source.interactors.auth_login import AuthLoginInteractor
from source.schemas.pydantic.auth import UserLoginRequest
from source.services.auth import AuthService


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, execute_results: list | None = None) -> None:
        self.execute_results = execute_results or []
        self.added = []

    async def execute(self, statement):
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        if self.added and self.added[-1].id is None:
            self.added[-1].id = 1


def build_user(
    *,
    auth_service: AuthService,
    password: str = "StrongPassword123",
    is_active: bool = True,
) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash=auth_service.hash_password(password),
        role=UserRole.CUSTOMER,
        is_active=is_active,
    )
    user.id = 1
    return user


@pytest.mark.asyncio
async def test_login_user_by_phone_success() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[build_user(auth_service=auth_service)])

    response = await AuthLoginInteractor().execute(
        session=session,
        auth_service=auth_service,
        data=UserLoginRequest(login="+79990000000", password="StrongPassword123"),
    )

    assert response.user.id == 1
    assert response.user.phone == "+79990000000"
    assert response.access_token
    assert response.refresh_token
    assert response.token_type == "bearer"
    assert isinstance(session.added[0], RefreshToken)
    assert session.added[0].token_hash != response.refresh_token


@pytest.mark.asyncio
async def test_login_user_by_email_success() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[build_user(auth_service=auth_service)])

    response = await AuthLoginInteractor().execute(
        session=session,
        auth_service=auth_service,
        data=UserLoginRequest(login="ivan@example.com", password="StrongPassword123"),
    )

    assert response.user.email == "ivan@example.com"
    assert response.access_token
    assert response.refresh_token


@pytest.mark.asyncio
async def test_login_user_with_wrong_password() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[build_user(auth_service=auth_service)])

    with pytest.raises(InvalidCredentialsError):
        await AuthLoginInteractor().execute(
            session=session,
            auth_service=auth_service,
            data=UserLoginRequest(login="+79990000000", password="WrongPassword123"),
        )


@pytest.mark.asyncio
async def test_login_user_not_found() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[None])

    with pytest.raises(InvalidCredentialsError):
        await AuthLoginInteractor().execute(
            session=session,
            auth_service=auth_service,
            data=UserLoginRequest(login="+79990000000", password="StrongPassword123"),
        )


@pytest.mark.asyncio
async def test_login_user_inactive() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[build_user(auth_service=auth_service, is_active=False)])

    with pytest.raises(InactiveUserError):
        await AuthLoginInteractor().execute(
            session=session,
            auth_service=auth_service,
            data=UserLoginRequest(login="+79990000000", password="StrongPassword123"),
        )


@pytest.mark.asyncio
async def test_login_response_does_not_include_password_hash() -> None:
    auth_service = AuthService()
    session = FakeSession(execute_results=[build_user(auth_service=auth_service)])

    response = await AuthLoginInteractor().execute(
        session=session,
        auth_service=auth_service,
        data=UserLoginRequest(login="+79990000000", password="StrongPassword123"),
    )

    response_data = response.model_dump()
    assert "password" not in response_data["user"]
    assert "password_hash" not in response_data["user"]
