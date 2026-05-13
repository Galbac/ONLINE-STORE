from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    AddressAccessDeniedError,
    AddressActiveOrderExistsError,
    AddressNotFoundError,
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserAddressesLimitExceededError,
)
from source.schemas.pydantic.profile import (
    AddressCreateRequest,
    AddressListQueryParams,
    AddressListResponse,
    AddressResponse,
    AddressUpdateRequest,
    ProfileOrderListQueryParams,
    ProfileOrderListResponse,
    ProfileAddressShortResponse,
    ProfileOrderShortResponse,
    ProfileSummaryResponse,
)
from source.services.auth import AuthService
from source.services.profile import ProfileService
from source.services.profile_cache import ProfileCacheService
from source.utils.query_hash import build_query_hash


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)
        self.ttls.pop(key, None)

    async def delete_by_pattern(self, pattern: str) -> None:
        prefix = pattern.removesuffix("*")
        keys = [key for key in self.values if key.startswith(prefix)]
        for key in keys:
            await self.delete(key)

    async def exists(self, key: str) -> bool:
        return key in self.values


class FakeUserRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.requested_user_id: int | None = None

    async def get_by_id(self, *, session, user_id: int) -> User | None:
        self.requested_user_id = user_id
        return self.user


class FakeAddressRepository:
    def __init__(self, addresses: list[AddressResponse] | None = None) -> None:
        self.default_address = ProfileAddressShortResponse(
            id=5,
            city="Москва",
            street="Тверская",
            house="10",
            apartment="15",
        )
        self.addresses = addresses if addresses is not None else [
            build_address(address_id=5, is_default=True),
            build_address(address_id=4, is_default=False),
        ]
        self.count = len(self.addresses)
        self.requested_user_id: int | None = None
        self.include_deleted: bool | None = None
        self.created_user_id: int | None = None
        self.unset_default_called = False
        self.updated_address_id: int | None = None
        self.soft_deleted_address_id: int | None = None
        self.default_address_id: int | None = None

    async def get_default_by_user_id(self, *, session, user_id: int):
        return self.default_address

    async def count_by_user_id(self, *, session, user_id: int, include_deleted: bool = False) -> int:
        return len(self._visible_addresses(include_deleted=include_deleted))

    async def get_by_user_id(
        self,
        *,
        session,
        user_id: int,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AddressResponse]:
        self.requested_user_id = user_id
        self.include_deleted = include_deleted
        visible_addresses = self._visible_addresses(include_deleted=include_deleted)
        visible_addresses.sort(key=lambda address: (not address.is_default, -address.created_at.timestamp()))
        return visible_addresses[offset : offset + limit]

    def _visible_addresses(self, *, include_deleted: bool) -> list[AddressResponse]:
        if include_deleted:
            return list(self.addresses)
        return [address for address in self.addresses if "deleted" not in (address.title or "").lower()]

    async def unset_default_by_user_id(self, *, session, user_id: int) -> None:
        self.unset_default_called = True
        self.addresses = [
            address.model_copy(update={"is_default": False})
            for address in self.addresses
        ]

    async def create(self, *, session, user_id: int, data: AddressCreateRequest, is_default: bool) -> AddressResponse:
        self.created_user_id = user_id
        address = AddressResponse(
            id=len(self.addresses) + 1,
            title=data.title,
            city=data.city,
            street=data.street,
            house=data.house,
            building=data.building,
            apartment=data.apartment,
            entrance=data.entrance,
            floor=data.floor,
            intercom=data.intercom,
            comment=data.comment,
            is_default=is_default,
            created_at=datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC),
        )
        object.__setattr__(address, "user_id", user_id)
        object.__setattr__(address, "is_deleted", False)
        self.addresses.append(address)
        return address

    async def get_by_id(self, *, session, address_id: int):
        for address in self.addresses:
            if address.id == address_id:
                return address
        return None

    async def update(self, *, session, address, data: AddressUpdateRequest) -> AddressResponse:
        self.updated_address_id = address.id
        updated_address = address.model_copy(update=data.model_dump(exclude_unset=True))
        if hasattr(address, "user_id"):
            object.__setattr__(updated_address, "user_id", address.user_id)
        if hasattr(address, "is_deleted"):
            object.__setattr__(updated_address, "is_deleted", address.is_deleted)
        self.addresses = [
            updated_address if item.id == address.id else item
            for item in self.addresses
        ]
        return updated_address

    async def soft_delete(self, *, session, address) -> None:
        self.soft_deleted_address_id = address.id
        object.__setattr__(address, "is_deleted", True)
        updated_address = address.model_copy(update={"is_default": False})
        object.__setattr__(updated_address, "user_id", address.user_id)
        object.__setattr__(updated_address, "is_deleted", True)
        self.addresses = [
            updated_address if item.id == address.id else item
            for item in self.addresses
        ]

    async def get_first_active_by_user_id(self, *, session, user_id: int, exclude_address_id: int | None = None):
        for address in self.addresses:
            if address.user_id == user_id and not address.is_deleted and address.id != exclude_address_id:
                return address
        return None

    async def set_default(self, *, session, address) -> None:
        self.default_address_id = address.id
        updated_address = address.model_copy(update={"is_default": True})
        object.__setattr__(updated_address, "user_id", address.user_id)
        object.__setattr__(updated_address, "is_deleted", address.is_deleted)
        self.addresses = [
            updated_address if item.id == address.id else item
            for item in self.addresses
        ]


class FakeOrderRepository:
    def __init__(
        self,
        *,
        has_active_orders_by_address: bool = False,
        orders: list[ProfileOrderShortResponse] | None = None,
    ) -> None:
        self.has_active_orders_by_address = has_active_orders_by_address
        self.orders = orders if orders is not None else [
            build_order(order_id=101, status="assembling", payment_status="paid", delivery_type="delivery"),
            build_order(order_id=100, status="completed", payment_status="paid", delivery_type="pickup"),
        ]
        self.count = len(self.orders)
        self.requested_user_id: int | None = None
        self.query: ProfileOrderListQueryParams | None = None
        self.active_order = self.orders[0]
        self.recent_orders = self.orders
        self.recent_limit: int | None = None

    async def count_by_user_id(self, *, session, user_id: int, query: ProfileOrderListQueryParams | None = None) -> int:
        return len(self._filter_orders(user_id=user_id, query=query))

    async def get_by_user_id(self, *, session, user_id: int, query: ProfileOrderListQueryParams):
        self.requested_user_id = user_id
        self.query = query
        filtered_orders = self._filter_orders(user_id=user_id, query=query)
        filtered_orders.sort(key=lambda order: order.created_at, reverse=True)
        return filtered_orders[query.offset : query.offset + query.limit]

    async def get_recent_by_user_id(self, *, session, user_id: int, limit: int = 5):
        self.recent_limit = limit
        return self.recent_orders

    async def get_active_by_user_id(self, *, session, user_id: int):
        return self.active_order

    async def has_active_orders_by_address_id(self, *, session, address_id: int) -> bool:
        return self.has_active_orders_by_address

    def _filter_orders(
        self,
        *,
        user_id: int,
        query: ProfileOrderListQueryParams | None,
    ) -> list[ProfileOrderShortResponse]:
        filtered_orders = [order for order in self.orders if getattr(order, "user_id", user_id) == user_id]
        if query is None:
            return filtered_orders
        if query.status is not None:
            filtered_orders = [order for order in filtered_orders if order.status == query.status]
        if query.payment_status is not None:
            filtered_orders = [order for order in filtered_orders if order.payment_status == query.payment_status]
        if query.delivery_type is not None:
            filtered_orders = [order for order in filtered_orders if order.delivery_type == query.delivery_type]
        if query.date_from is not None:
            filtered_orders = [order for order in filtered_orders if order.created_at.date() >= query.date_from]
        if query.date_to is not None:
            filtered_orders = [order for order in filtered_orders if order.created_at.date() <= query.date_to]
        return filtered_orders


def build_user(*, user_id: int = 1, is_active: bool = True, is_deleted: bool = False) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email="ivan@example.com",
        password_hash="password_hash",
        role=UserRole.CUSTOMER,
        is_active=is_active,
        is_deleted=is_deleted,
    )
    user.id = user_id
    user.created_date = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    user.updated_date = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    user.deleted_at = None
    return user


def build_address(
    *,
    address_id: int,
    title: str = "Дом",
    user_id: int = 1,
    is_default: bool = False,
    is_deleted: bool = False,
    created_at: datetime | None = None,
) -> AddressResponse:
    created_at = created_at or datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    address = AddressResponse(
        id=address_id,
        title=title,
        city="Москва",
        street="Тверская",
        house="10",
        building="1",
        apartment="15",
        entrance="2",
        floor="5",
        intercom="15К",
        comment="Позвонить за 10 минут",
        is_default=is_default,
        created_at=created_at,
        updated_at=created_at,
    )
    object.__setattr__(address, "user_id", user_id)
    object.__setattr__(address, "is_deleted", is_deleted)
    return address


def build_order(
    *,
    order_id: int,
    user_id: int = 1,
    status: str = "assembling",
    payment_status: str = "paid",
    delivery_type: str = "delivery",
    created_at: datetime | None = None,
) -> ProfileOrderShortResponse:
    created_at = created_at or datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)
    order = ProfileOrderShortResponse(
        id=order_id,
        order_number=f"ORD-{order_id}",
        status=status,
        payment_method="online",
        payment_status=payment_status,
        delivery_type=delivery_type,
        final_price=Decimal("3250.50"),
        items_count=8,
        created_at=created_at,
    )
    object.__setattr__(order, "user_id", user_id)
    return order


async def execute_get_profile_summary(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    address_repository: FakeAddressRepository | None = None,
    order_repository: FakeOrderRepository | None = None,
    user_id: int = 1,
) -> ProfileSummaryResponse:
    return await ProfileService().get_profile_summary(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        address_repository=address_repository or FakeAddressRepository(),
        order_repository=order_repository or FakeOrderRepository(),
        user_id=user_id,
    )


async def execute_get_user_orders(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    order_repository: FakeOrderRepository | None = None,
    user_id: int = 1,
    query: ProfileOrderListQueryParams | None = None,
) -> ProfileOrderListResponse:
    return await ProfileService().get_user_orders(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        order_repository=order_repository or FakeOrderRepository(),
        user_id=user_id,
        query=query or ProfileOrderListQueryParams(),
    )


async def execute_get_user_addresses(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    address_repository: FakeAddressRepository | None = None,
    user_id: int = 1,
    query: AddressListQueryParams | None = None,
) -> AddressListResponse:
    return await ProfileService().get_user_addresses(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        address_repository=address_repository or FakeAddressRepository(),
        user_id=user_id,
        query=query or AddressListQueryParams(),
    )


async def execute_create_address(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    address_repository: FakeAddressRepository | None = None,
    user_id: int = 1,
    data: AddressCreateRequest | None = None,
) -> AddressResponse:
    return await ProfileService().create_address(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        address_repository=address_repository or FakeAddressRepository(),
        user_id=user_id,
        data=data or AddressCreateRequest(
            title="Дом",
            city="Москва",
            street="Тверская",
            house="10",
            building="1",
            apartment="15",
            entrance="2",
            floor="5",
            intercom="15К",
            comment="Позвонить за 10 минут",
            is_default=False,
        ),
    )


async def execute_update_address(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    address_repository: FakeAddressRepository | None = None,
    user_id: int = 1,
    address_id: int = 1,
    data: AddressUpdateRequest | None = None,
) -> AddressResponse:
    return await ProfileService().update_address(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        address_repository=address_repository or FakeAddressRepository(),
        user_id=user_id,
        address_id=address_id,
        data=data or AddressUpdateRequest(title="Работа"),
    )


async def execute_delete_address(
    *,
    user_repository: FakeUserRepository,
    redis_service: FakeRedisService | None = None,
    address_repository: FakeAddressRepository | None = None,
    order_repository: FakeOrderRepository | None = None,
    user_id: int = 1,
    address_id: int = 1,
) -> None:
    await ProfileService().delete_address(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        profile_cache_service=ProfileCacheService(),
        user_repository=user_repository,
        address_repository=address_repository or FakeAddressRepository(),
        order_repository=order_repository or FakeOrderRepository(),
        user_id=user_id,
        address_id=address_id,
    )


@pytest.mark.asyncio
async def test_get_profile_summary_from_postgresql_success() -> None:
    user_repository = FakeUserRepository(build_user())
    order_repository = FakeOrderRepository()

    response = await execute_get_profile_summary(
        user_repository=user_repository,
        order_repository=order_repository,
    )

    assert response.user.id == 1
    assert response.user.email == "ivan@example.com"
    assert response.stats.orders_count == 2
    assert response.stats.addresses_count == 2
    assert response.default_address is not None
    assert response.active_order is not None
    assert response.recent_orders[0].order_number == "ORD-101"
    assert order_repository.recent_limit == 5


@pytest.mark.asyncio
async def test_get_profile_orders_from_postgresql_success() -> None:
    response = await execute_get_user_orders(user_repository=FakeUserRepository(build_user()))

    assert response.total == 2
    assert response.limit == 20
    assert response.offset == 0
    assert response.items[0].id == 101
    assert response.items[0].payment_method == "online"
    assert response.items[0].items_count == 8


@pytest.mark.asyncio
async def test_get_profile_orders_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProfileOrderListQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = ProfileOrderListResponse(
        items=[build_order(order_id=101)],
        total=1,
        limit=20,
        offset=0,
    )
    redis_service.values[f"profile:orders:1:{query_hash}"] = cached_response.model_dump_json()
    user_repository = FakeUserRepository(None)

    response = await execute_get_user_orders(
        user_repository=user_repository,
        redis_service=redis_service,
        query=query,
    )

    assert response.total == 1
    assert user_repository.requested_user_id is None


@pytest.mark.asyncio
async def test_get_profile_orders_filter_by_status() -> None:
    order_repository = FakeOrderRepository()

    response = await execute_get_user_orders(
        user_repository=FakeUserRepository(build_user()),
        order_repository=order_repository,
        query=ProfileOrderListQueryParams(status="completed"),
    )

    assert [order.status for order in response.items] == ["completed"]
    assert order_repository.query is not None
    assert order_repository.query.status == "completed"


@pytest.mark.asyncio
async def test_get_profile_orders_filter_by_payment_status() -> None:
    order_repository = FakeOrderRepository(
        orders=[
            build_order(order_id=1, payment_status="paid"),
            build_order(order_id=2, payment_status="pending"),
        ],
    )

    response = await execute_get_user_orders(
        user_repository=FakeUserRepository(build_user()),
        order_repository=order_repository,
        query=ProfileOrderListQueryParams(payment_status="pending"),
    )

    assert [order.payment_status for order in response.items] == ["pending"]


@pytest.mark.asyncio
async def test_get_profile_orders_filter_by_delivery_type() -> None:
    response = await execute_get_user_orders(
        user_repository=FakeUserRepository(build_user()),
        query=ProfileOrderListQueryParams(delivery_type="pickup"),
    )

    assert [order.delivery_type for order in response.items] == ["pickup"]


@pytest.mark.asyncio
async def test_get_profile_orders_pagination() -> None:
    order_repository = FakeOrderRepository(
        orders=[
            build_order(order_id=1, created_at=datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)),
            build_order(order_id=2, created_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)),
            build_order(order_id=3, created_at=datetime(2026, 5, 11, 10, 0, 0, tzinfo=UTC)),
        ],
    )

    response = await execute_get_user_orders(
        user_repository=FakeUserRepository(build_user()),
        order_repository=order_repository,
        query=ProfileOrderListQueryParams(limit=1, offset=1),
    )

    assert response.total == 3
    assert response.limit == 1
    assert response.offset == 1
    assert [order.id for order in response.items] == [2]


@pytest.mark.asyncio
async def test_get_profile_orders_uses_current_user_id_only() -> None:
    order_repository = FakeOrderRepository(
        orders=[
            build_order(order_id=1, user_id=7),
            build_order(order_id=2, user_id=1),
        ],
    )

    response = await execute_get_user_orders(
        user_repository=FakeUserRepository(build_user(user_id=7)),
        order_repository=order_repository,
        user_id=7,
    )

    assert order_repository.requested_user_id == 7
    assert [order.id for order in response.items] == [1]


@pytest.mark.asyncio
async def test_get_profile_orders_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


def test_get_profile_orders_with_invalid_query_params() -> None:
    with pytest.raises(ValidationError):
        ProfileOrderListQueryParams(delivery_type="courier")


@pytest.mark.asyncio
async def test_get_profile_orders_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProfileOrderListQueryParams(status="assembling")

    await execute_get_user_orders(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
        query=query,
    )

    cache_key = f"profile:orders:1:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.profile_orders.cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_profile_summary_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    cached_response = ProfileSummaryResponse(
        user={
            "id": 1,
            "name": "Иван Иванов",
            "phone": "+79990000000",
            "email": "ivan@example.com",
            "role": UserRole.CUSTOMER,
            "is_active": True,
            "is_verified": False,
        },
        stats={"orders_count": 1, "addresses_count": 0},
        default_address=None,
        active_order=None,
        recent_orders=[],
    )
    redis_service.values["profile:summary:1"] = cached_response.model_dump_json()
    user_repository = FakeUserRepository(None)

    response = await execute_get_profile_summary(
        user_repository=user_repository,
        redis_service=redis_service,
    )

    assert response.stats.orders_count == 1
    assert user_repository.requested_user_id is None


@pytest.mark.asyncio
async def test_get_profile_summary_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_summary_with_invalid_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization="Bearer invalid-token", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_summary_with_refresh_token_instead_of_access_token() -> None:
    refresh_token = AuthService().create_refresh_token(user_id=1, role=UserRole.CUSTOMER)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=f"Bearer {refresh_token}", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_summary_user_not_found() -> None:
    with pytest.raises(CurrentUserNotFoundError):
        await execute_get_profile_summary(user_repository=FakeUserRepository(None))


@pytest.mark.asyncio
async def test_get_profile_summary_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        await execute_get_profile_summary(user_repository=FakeUserRepository(build_user(is_active=False)))


@pytest.mark.asyncio
async def test_get_profile_summary_deleted_user() -> None:
    with pytest.raises(InactiveUserError):
        await execute_get_profile_summary(user_repository=FakeUserRepository(build_user(is_deleted=True)))


@pytest.mark.asyncio
async def test_get_profile_summary_uses_current_user_id_only() -> None:
    user_repository = FakeUserRepository(build_user(user_id=7))

    await execute_get_profile_summary(user_repository=user_repository, user_id=7)

    assert user_repository.requested_user_id == 7


@pytest.mark.asyncio
async def test_get_profile_summary_response_does_not_include_password_hash() -> None:
    response = await execute_get_profile_summary(user_repository=FakeUserRepository(build_user()))

    response_data = response.model_dump()
    assert "password_hash" not in response_data
    assert "refresh_token" not in response_data


@pytest.mark.asyncio
async def test_get_profile_summary_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()

    await execute_get_profile_summary(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
    )

    assert "profile:summary:1" in redis_service.values
    assert redis_service.ttls["profile:summary:1"] == settings.profile_summary.cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_profile_addresses_from_postgresql_success() -> None:
    response = await execute_get_user_addresses(user_repository=FakeUserRepository(build_user()))

    assert response.total == 2
    assert response.limit == 50
    assert response.offset == 0
    assert response.items[0].id == 5
    assert response.items[0].is_default is True


@pytest.mark.asyncio
async def test_get_profile_addresses_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    cached_response = AddressListResponse(
        items=[build_address(address_id=5, is_default=True)],
        total=1,
        limit=50,
        offset=0,
    )
    redis_service.values[
        "profile:addresses:1:include_deleted:false:limit:50:offset:0"
    ] = cached_response.model_dump_json()
    user_repository = FakeUserRepository(None)

    response = await execute_get_user_addresses(
        user_repository=user_repository,
        redis_service=redis_service,
    )

    assert response.total == 1
    assert user_repository.requested_user_id is None


@pytest.mark.asyncio
async def test_get_profile_addresses_uses_current_user_id_only() -> None:
    address_repository = FakeAddressRepository()

    await execute_get_user_addresses(
        user_repository=FakeUserRepository(build_user(user_id=7)),
        address_repository=address_repository,
        user_id=7,
    )

    assert address_repository.requested_user_id == 7


@pytest.mark.asyncio
async def test_get_profile_addresses_excludes_deleted_by_default() -> None:
    address_repository = FakeAddressRepository(
        addresses=[
            build_address(address_id=1, title="Дом"),
            build_address(address_id=2, title="Deleted address"),
        ],
    )

    response = await execute_get_user_addresses(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
    )

    assert [address.id for address in response.items] == [1]
    assert response.total == 1
    assert address_repository.include_deleted is False


@pytest.mark.asyncio
async def test_get_profile_addresses_include_deleted() -> None:
    address_repository = FakeAddressRepository(
        addresses=[
            build_address(address_id=1, title="Дом"),
            build_address(address_id=2, title="Deleted address"),
        ],
    )

    response = await execute_get_user_addresses(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
        query=AddressListQueryParams(include_deleted=True),
    )

    assert [address.id for address in response.items] == [1, 2]
    assert response.total == 2


@pytest.mark.asyncio
async def test_get_profile_addresses_default_address_first() -> None:
    address_repository = FakeAddressRepository(
        addresses=[
            build_address(address_id=1, is_default=False, created_at=datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)),
            build_address(address_id=2, is_default=True, created_at=datetime(2026, 5, 10, 10, 0, 0, tzinfo=UTC)),
        ],
    )

    response = await execute_get_user_addresses(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
    )

    assert response.items[0].id == 2
    assert response.items[0].is_default is True


@pytest.mark.asyncio
async def test_get_profile_addresses_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_addresses_with_invalid_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization="Bearer invalid-token", redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_addresses_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()

    await execute_get_user_addresses(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
    )

    cache_key = "profile:addresses:1:include_deleted:false:limit:50:offset:0"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.profile_addresses.cache_ttl_seconds


@pytest.mark.asyncio
async def test_create_profile_address_success() -> None:
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1)])

    response = await execute_create_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
    )

    assert response.id == 2
    assert response.city == "Москва"
    assert response.street == "Тверская"
    assert response.house == "10"
    assert address_repository.created_user_id == 1


@pytest.mark.asyncio
async def test_create_profile_address_first_address_becomes_default() -> None:
    address_repository = FakeAddressRepository(addresses=[])

    response = await execute_create_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
        data=AddressCreateRequest(city="Москва", street="Тверская", house="10"),
    )

    assert response.is_default is True
    assert address_repository.unset_default_called is True


@pytest.mark.asyncio
async def test_create_profile_address_with_default_unsets_other_defaults() -> None:
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1, is_default=True)])

    response = await execute_create_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
        data=AddressCreateRequest(city="Москва", street="Тверская", house="10", is_default=True),
    )

    assert response.is_default is True
    assert address_repository.unset_default_called is True
    assert address_repository.addresses[0].is_default is False


@pytest.mark.asyncio
async def test_create_profile_address_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


def test_create_profile_address_with_empty_city() -> None:
    with pytest.raises(ValidationError):
        AddressCreateRequest(city="   ", street="Тверская", house="10")


def test_create_profile_address_with_empty_street() -> None:
    with pytest.raises(ValidationError):
        AddressCreateRequest(city="Москва", street="   ", house="10")


def test_create_profile_address_with_empty_house() -> None:
    with pytest.raises(ValidationError):
        AddressCreateRequest(city="Москва", street="Тверская", house="   ")


@pytest.mark.asyncio
async def test_create_profile_address_limit_exceeded(monkeypatch) -> None:
    monkeypatch.setattr(settings.profile_addresses, "user_addresses_limit", 1)
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1)])

    with pytest.raises(UserAddressesLimitExceededError):
        await execute_create_address(
            user_repository=FakeUserRepository(build_user()),
            address_repository=address_repository,
        )


@pytest.mark.asyncio
async def test_create_profile_address_ignores_body_user_id() -> None:
    address_repository = FakeAddressRepository(addresses=[])
    data = AddressCreateRequest.model_validate(
        {"city": "Москва", "street": "Тверская", "house": "10", "user_id": 999},
    )

    await execute_create_address(
        user_repository=FakeUserRepository(build_user(user_id=7)),
        address_repository=address_repository,
        user_id=7,
        data=data,
    )

    assert address_repository.created_user_id == 7


@pytest.mark.asyncio
async def test_create_profile_address_invalidates_redis_cache() -> None:
    redis_service = FakeRedisService()
    redis_service.values["profile:addresses:1:include_deleted:false:limit:50:offset:0"] = "{}"
    redis_service.values["profile:summary:1"] = "{}"

    await execute_create_address(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
        address_repository=FakeAddressRepository(addresses=[]),
    )

    assert "profile:addresses:1:include_deleted:false:limit:50:offset:0" in redis_service.deleted
    assert "profile:summary:1" in redis_service.deleted


@pytest.mark.asyncio
async def test_update_profile_address_success() -> None:
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1)])

    response = await execute_update_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
        data=AddressUpdateRequest(
            title="Работа",
            city="Москва",
            street="Арбат",
            house="20",
            building=None,
            apartment="8",
            entrance="1",
            floor="3",
            intercom="8",
            comment="Вход со двора",
        ),
    )

    assert response.id == 1
    assert response.title == "Работа"
    assert response.street == "Арбат"
    assert response.house == "20"
    assert address_repository.updated_address_id == 1


@pytest.mark.asyncio
async def test_update_profile_address_set_default_success() -> None:
    address_repository = FakeAddressRepository(
        addresses=[
            build_address(address_id=1, is_default=False),
            build_address(address_id=2, is_default=True),
        ],
    )

    response = await execute_update_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
        data=AddressUpdateRequest(is_default=True),
    )

    assert response.is_default is True
    assert address_repository.unset_default_called is True


@pytest.mark.asyncio
async def test_update_profile_address_with_default_unsets_other_defaults() -> None:
    address_repository = FakeAddressRepository(
        addresses=[
            build_address(address_id=1, is_default=False),
            build_address(address_id=2, is_default=True),
        ],
    )

    await execute_update_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
        data=AddressUpdateRequest(is_default=True),
    )

    other_address = next(address for address in address_repository.addresses if address.id == 2)
    assert other_address.is_default is False


@pytest.mark.asyncio
async def test_update_profile_address_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_update_profile_address_not_found() -> None:
    with pytest.raises(AddressNotFoundError):
        await execute_update_address(
            user_repository=FakeUserRepository(build_user()),
            address_repository=FakeAddressRepository(addresses=[]),
        )


@pytest.mark.asyncio
async def test_update_profile_address_access_denied() -> None:
    with pytest.raises(AddressAccessDeniedError):
        await execute_update_address(
            user_repository=FakeUserRepository(build_user(user_id=1)),
            address_repository=FakeAddressRepository(addresses=[build_address(address_id=1, user_id=2)]),
        )


@pytest.mark.asyncio
async def test_update_profile_address_without_fields() -> None:
    with pytest.raises(EmptyUserProfileUpdateError):
        await execute_update_address(
            user_repository=FakeUserRepository(build_user()),
            data=AddressUpdateRequest(),
        )


@pytest.mark.asyncio
async def test_update_profile_address_ignores_body_user_id() -> None:
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1, user_id=7)])
    data = AddressUpdateRequest.model_validate({"title": "Работа", "user_id": 999})

    await execute_update_address(
        user_repository=FakeUserRepository(build_user(user_id=7)),
        address_repository=address_repository,
        user_id=7,
        data=data,
    )

    updated_address = address_repository.addresses[0]
    assert updated_address.user_id == 7
    assert updated_address.title == "Работа"


@pytest.mark.asyncio
async def test_update_profile_address_invalidates_redis_cache() -> None:
    redis_service = FakeRedisService()
    redis_service.values["profile:addresses:1:include_deleted:false:limit:50:offset:0"] = "{}"
    redis_service.values["profile:summary:1"] = "{}"

    await execute_update_address(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
        address_repository=FakeAddressRepository(addresses=[build_address(address_id=1)]),
    )

    assert "profile:addresses:1:include_deleted:false:limit:50:offset:0" in redis_service.deleted
    assert "profile:summary:1" in redis_service.deleted


@pytest.mark.asyncio
async def test_delete_profile_address_soft_delete_success() -> None:
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1)])

    await execute_delete_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
    )

    assert address_repository.soft_deleted_address_id == 1
    assert address_repository.addresses[0].is_deleted is True


@pytest.mark.asyncio
async def test_delete_profile_address_without_access_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_delete_profile_address_not_found() -> None:
    with pytest.raises(AddressNotFoundError):
        await execute_delete_address(
            user_repository=FakeUserRepository(build_user()),
            address_repository=FakeAddressRepository(addresses=[]),
        )


@pytest.mark.asyncio
async def test_delete_profile_address_access_denied() -> None:
    with pytest.raises(AddressAccessDeniedError):
        await execute_delete_address(
            user_repository=FakeUserRepository(build_user(user_id=1)),
            address_repository=FakeAddressRepository(addresses=[build_address(address_id=1, user_id=2)]),
        )


@pytest.mark.asyncio
async def test_delete_profile_address_already_deleted() -> None:
    with pytest.raises(AddressNotFoundError):
        await execute_delete_address(
            user_repository=FakeUserRepository(build_user()),
            address_repository=FakeAddressRepository(addresses=[build_address(address_id=1, is_deleted=True)]),
        )


@pytest.mark.asyncio
async def test_delete_profile_default_address_assigns_another_default() -> None:
    address_repository = FakeAddressRepository(
        addresses=[
            build_address(address_id=1, is_default=True),
            build_address(address_id=2, is_default=False),
        ],
    )

    await execute_delete_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
    )

    assert address_repository.default_address_id == 2


@pytest.mark.asyncio
async def test_delete_profile_default_address_without_other_addresses() -> None:
    address_repository = FakeAddressRepository(addresses=[build_address(address_id=1, is_default=True)])

    await execute_delete_address(
        user_repository=FakeUserRepository(build_user()),
        address_repository=address_repository,
    )

    assert address_repository.default_address_id is None


@pytest.mark.asyncio
async def test_delete_profile_address_with_active_order() -> None:
    with pytest.raises(AddressActiveOrderExistsError):
        await execute_delete_address(
            user_repository=FakeUserRepository(build_user()),
            address_repository=FakeAddressRepository(addresses=[build_address(address_id=1)]),
            order_repository=FakeOrderRepository(has_active_orders_by_address=True),
        )


@pytest.mark.asyncio
async def test_delete_profile_address_invalidates_redis_cache() -> None:
    redis_service = FakeRedisService()
    redis_service.values["profile:addresses:1:include_deleted:false:limit:50:offset:0"] = "{}"
    redis_service.values["profile:summary:1"] = "{}"

    await execute_delete_address(
        user_repository=FakeUserRepository(build_user()),
        redis_service=redis_service,
        address_repository=FakeAddressRepository(addresses=[build_address(address_id=1)]),
    )

    assert "profile:addresses:1:include_deleted:false:limit:50:offset:0" in redis_service.deleted
    assert "profile:summary:1" in redis_service.deleted
