from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import require_admin_or_manager
from source.db.models.choises.enum import UserRole
from source.schemas.pydantic.notifications import TestEmailRequest


def test_test_email_request_invalid_email_error() -> None:
    with pytest.raises(ValidationError):
        TestEmailRequest(email="invalid-email")


@pytest.mark.asyncio
async def test_require_admin_or_manager_forbidden_for_customer() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_or_manager(SimpleNamespace(role=UserRole.CUSTOMER))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Недостаточно прав"


@pytest.mark.asyncio
async def test_require_admin_or_manager_allows_manager() -> None:
    user = SimpleNamespace(role=UserRole.MANAGER)

    assert await require_admin_or_manager(user) is user
