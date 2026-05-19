import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import resolve_access_token
from source.schemas.pydantic.admin_auth import AdminLoginRequest


def test_admin_login_request_accepts_email() -> None:
    request = AdminLoginRequest(login=" ADMIN@EXAMPLE.COM ", password="StrongPassword123")

    assert request.login == "admin@example.com"


def test_admin_login_request_accepts_phone() -> None:
    request = AdminLoginRequest(login="+79990000000", password="StrongPassword123")

    assert request.login == "+79990000000"


def test_admin_login_request_invalid_login_error() -> None:
    with pytest.raises(ValidationError):
        AdminLoginRequest(login="not-login", password="StrongPassword123")


@pytest.mark.asyncio
async def test_admin_logout_without_access_token_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None)

    assert exc_info.value.status_code == 401
