from unittest.mock import AsyncMock

import pytest

from source.errors.auth import (
    RegisterOtpExpiredError,
    RegisterOtpInvalidError,
    RegisterOtpMaxAttemptsError,
    UserEmailAlreadyExistsError,
)
from source.schemas.pydantic.auth import SendRegisterOtpRequest
from source.services.auth import AuthService


class FakeScalarResult:
    def __init__(self, value: int | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> int | None:
        return self.value


class FakeSession:
    def __init__(self, execute_results: list[int | None] | None = None) -> None:
        self.execute_results = execute_results or []

    async def execute(self, statement):
        val = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(val)


@pytest.mark.asyncio
async def test_send_register_otp_generates_and_stores_code():
    auth_service = AuthService()
    session = FakeSession()
    redis_service = AsyncMock()
    redis_service.incr.return_value = 1
    email_service = AsyncMock()

    request = SendRegisterOtpRequest(email="test@example.com")
    response = await auth_service.send_register_otp(
        session=session,
        redis_service=redis_service,
        email_service=email_service,
        data=request,
        ip_address="127.0.0.1",
    )

    assert response.email == "test@example.com"
    assert redis_service.set.call_count >= 2
    assert email_service.send_register_otp_email.called


@pytest.mark.asyncio
async def test_send_register_otp_fails_if_email_exists():
    auth_service = AuthService()
    session = FakeSession(execute_results=[1])  # email exists
    redis_service = AsyncMock()
    email_service = AsyncMock()

    request = SendRegisterOtpRequest(email="existing@example.com")
    with pytest.raises(UserEmailAlreadyExistsError):
        await auth_service.send_register_otp(
            session=session,
            redis_service=redis_service,
            email_service=email_service,
            data=request,
            ip_address="127.0.0.1",
        )


@pytest.mark.asyncio
async def test_verify_register_otp_success():
    auth_service = AuthService()
    redis_service = AsyncMock()
    redis_service.get.side_effect = lambda key: b"4829" if "code" in key else b"0"

    await auth_service.verify_register_otp(
        redis_service=redis_service,
        email="test@example.com",
        otp_code="4829",
    )
    assert redis_service.delete.called


@pytest.mark.asyncio
async def test_verify_register_otp_expired():
    auth_service = AuthService()
    redis_service = AsyncMock()
    redis_service.get.return_value = None

    with pytest.raises(RegisterOtpExpiredError):
        await auth_service.verify_register_otp(
            redis_service=redis_service,
            email="test@example.com",
            otp_code="4829",
        )


@pytest.mark.asyncio
async def test_verify_register_otp_invalid_code():
    auth_service = AuthService()
    redis_service = AsyncMock()
    redis_service.get.side_effect = lambda key: b"4829" if "code" in key else b"0"

    with pytest.raises(RegisterOtpInvalidError):
        await auth_service.verify_register_otp(
            redis_service=redis_service,
            email="test@example.com",
            otp_code="1111",
        )
    assert redis_service.incr.called


@pytest.mark.asyncio
async def test_verify_register_otp_max_attempts():
    auth_service = AuthService()
    redis_service = AsyncMock()
    redis_service.get.side_effect = lambda key: b"4829" if "code" in key else b"5"

    with pytest.raises(RegisterOtpMaxAttemptsError):
        await auth_service.verify_register_otp(
            redis_service=redis_service,
            email="test@example.com",
            otp_code="1111",
        )
