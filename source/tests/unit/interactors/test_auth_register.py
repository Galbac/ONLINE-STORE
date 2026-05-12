import pytest
from pydantic import ValidationError

from source.db.models.choises.enum import UserRole
from source.errors.auth import (
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.interactors.auth_register import AuthRegisterInteractor
from source.schemas.pydantic.auth import UserRegisterRequest
from source.services.auth import AuthService


class FakeScalarResult:
    def __init__(self, value: int | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> int | None:
        return self.value


class FakeSession:
    def __init__(self, execute_results: list[int | None] | None = None) -> None:
        self.execute_results = execute_results or []
        self.added = []

    async def execute(self, statement):
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        if self.added[-1].id is None:
            self.added[-1].id = 1

    async def refresh(self, instance) -> None:
        return None


def build_request(
    *,
    phone: str = "+79990000000",
    email: str | None = "ivan@example.com",
    password: str = "StrongPassword123",
) -> UserRegisterRequest:
    return UserRegisterRequest(
        name="Иван Иванов",
        phone=phone,
        email=email,
        password=password,
    )


@pytest.mark.asyncio
async def test_register_user_success() -> None:
    session = FakeSession()
    interactor = AuthRegisterInteractor()

    response = await interactor.execute(
        session=session,
        auth_service=AuthService(),
        data=build_request(),
    )

    assert response.id == 1
    assert response.name == "Иван Иванов"
    assert response.phone == "+79990000000"
    assert response.email == "ivan@example.com"
    assert response.role == UserRole.CUSTOMER
    assert response.is_active is True
    assert response.token_type == "bearer"
    assert response.access_token
    assert response.refresh_token
    assert session.added[0].password_hash != "StrongPassword123"


@pytest.mark.asyncio
async def test_register_user_with_existing_phone() -> None:
    session = FakeSession(execute_results=[1])
    interactor = AuthRegisterInteractor()

    with pytest.raises(UserPhoneAlreadyExistsError):
        await interactor.execute(
            session=session,
            auth_service=AuthService(),
            data=build_request(),
        )


@pytest.mark.asyncio
async def test_register_user_with_existing_email() -> None:
    session = FakeSession(execute_results=[None, 1])
    interactor = AuthRegisterInteractor()

    with pytest.raises(UserEmailAlreadyExistsError):
        await interactor.execute(
            session=session,
            auth_service=AuthService(),
            data=build_request(),
        )


def test_register_user_with_weak_password() -> None:
    with pytest.raises(ValidationError):
        build_request(password="1234567")


@pytest.mark.asyncio
async def test_register_response_does_not_include_password_hash() -> None:
    session = FakeSession()
    interactor = AuthRegisterInteractor()

    response = await interactor.execute(
        session=session,
        auth_service=AuthService(),
        data=build_request(),
    )

    response_data = response.model_dump()
    assert "password" not in response_data
    assert "password_hash" not in response_data
