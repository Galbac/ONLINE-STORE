from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.profile import (
    create_profile_address,
    delete_profile_address,
    get_profile_addresses,
    update_profile_address,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    AddressActiveOrderExistsError,
    AddressNotFoundError,
)
from source.schemas.pydantic.profile import (
    AddressCreateRequest,
    AddressListResponse,
    AddressResponse,
    AddressUpdateRequest,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)


@pytest.fixture
def fake_address():
    now = datetime.now(UTC)
    return AddressResponse(
        id=10,
        title="Дом",
        city="Кизляр",
        street="Ленина",
        house="45",
        apartment="12",
        is_default=True,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------
# GET /profile/addresses
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_profile_addresses_success(active_user, fake_address):
    service = AsyncMock()
    service.get_user_addresses.return_value = AddressListResponse(
        items=[fake_address],
        total=1,
        limit=50,
        offset=0,
    )

    response = await unwrap(get_profile_addresses)(
        current_user=active_user,
        include_deleted=False,
        limit=50,
        offset=0,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        profile_service=service,
        profile_cache_service=AsyncMock(),
        user_repository=AsyncMock(),
        address_repository=AsyncMock(),
    )

    assert response.total == 1
    assert response.items[0].city == "Кизляр"


# ---------------------------------------------------------
# POST /profile/addresses
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_create_profile_address_success(active_user, fake_address):
    service = AsyncMock()
    service.create_address.return_value = fake_address
    commiter = AsyncMock()

    body = AddressCreateRequest(
        title="Дом",
        city="Кизляр",
        street="Ленина",
        house="45",
        apartment="12",
        is_default=True,
    )

    response = await unwrap(create_profile_address)(
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        profile_service=service,
        profile_cache_service=AsyncMock(),
        user_repository=AsyncMock(),
        address_repository=AsyncMock(),
    )

    assert response.id == 10
    assert commiter.commit.called


# ---------------------------------------------------------
# PATCH /profile/addresses/{id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_update_profile_address_success(active_user, fake_address):
    service = AsyncMock()
    updated = fake_address.model_copy(update={"house": "47"})
    service.update_address.return_value = updated
    commiter = AsyncMock()

    body = AddressUpdateRequest(house="47")
    response = await unwrap(update_profile_address)(
        address_id=10,
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        profile_service=service,
        profile_cache_service=AsyncMock(),
        user_repository=AsyncMock(),
        address_repository=AsyncMock(),
    )

    assert response.house == "47"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_update_profile_address_not_found(active_user):
    service = AsyncMock()
    service.update_address.side_effect = AddressNotFoundError
    commiter = AsyncMock()

    body = AddressUpdateRequest(house="47")
    with pytest.raises(HTTPException) as exc:
        await unwrap(update_profile_address)(
            address_id=999,
            body=body,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            profile_service=service,
            profile_cache_service=AsyncMock(),
            user_repository=AsyncMock(),
            address_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404
    assert commiter.rollback.called


# ---------------------------------------------------------
# DELETE /profile/addresses/{id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_profile_address_success(active_user):
    service = AsyncMock()
    commiter = AsyncMock()

    response = await unwrap(delete_profile_address)(
        address_id=10,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        profile_service=service,
        profile_cache_service=AsyncMock(),
        user_repository=AsyncMock(),
        address_repository=AsyncMock(),
        order_repository=AsyncMock(),
    )

    assert response.message == "Адрес успешно удалён"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_delete_profile_address_active_order_conflict(active_user):
    service = AsyncMock()
    service.delete_address.side_effect = AddressActiveOrderExistsError
    commiter = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await unwrap(delete_profile_address)(
            address_id=10,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            profile_service=service,
            profile_cache_service=AsyncMock(),
            user_repository=AsyncMock(),
            address_repository=AsyncMock(),
            order_repository=AsyncMock(),
        )
    assert exc.value.status_code == 409
    assert commiter.rollback.called
