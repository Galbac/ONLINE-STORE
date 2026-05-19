import pytest
from pydantic import ValidationError

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
