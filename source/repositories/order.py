from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.order import Order
from source.schemas.pydantic.order import OrderMyListQueryParams, OrderShortResponse
from source.schemas.pydantic.admin_dashboard import AdminRecentOrderResponse
from source.schemas.pydantic.profile import ProfileOrderListQueryParams, ProfileOrderShortResponse


ACTIVE_ORDER_STATUSES = ("new", "paid", "assembling", "delivering", "in_progress")


class OrderRepository:
    async def create(self, *, session: AsyncSession, **data) -> Order:
        order = Order(**data)
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        order_id: int,
    ) -> Order | None:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def get_dashboard_stats(self, *, session: AsyncSession):
        today = datetime.now(settings.tz).date()
        today_from = datetime.combine(today, time.min)
        today_to = datetime.combine(today, time.max)
        result = await session.execute(
            select(
                func.count(Order.id).filter(Order.created_date.between(today_from, today_to)),
                func.count(Order.id).filter(Order.status == "new"),
                func.count(Order.id).filter(
                    Order.created_date.between(today_from, today_to),
                    Order.payment_status == "paid",
                ),
                func.coalesce(
                    func.sum(Order.final_price).filter(
                        Order.created_date.between(today_from, today_to),
                        Order.payment_status == "paid",
                    ),
                    0,
                ),
            ),
        )
        today_count, new_count, paid_today_count, sales_today_amount = result.one()
        return SimpleNamespace(
            today_count=int(today_count),
            new_count=int(new_count),
            paid_today_count=int(paid_today_count),
            sales_today_amount=Decimal(str(sales_today_amount)),
        )

    async def get_dashboard_recent_orders(
        self,
        *,
        session: AsyncSession,
        limit: int = 5,
    ) -> list[AdminRecentOrderResponse]:
        result = await session.execute(
            select(Order)
            .order_by(desc(Order.created_date))
            .limit(limit),
        )
        return [
            AdminRecentOrderResponse(
                id=order.id,
                order_number=order.order_number,
                status=order.status,
                final_price=order.final_price,
                created_at=order.created_date,
            )
            for order in result.scalars().all()
        ]

    async def get_status_by_id(self, *, session: AsyncSession, order_id: int) -> Order | None:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def update_status(self, *, session: AsyncSession, order: Order, status: str) -> Order:
        order.status = status
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

    async def update_payment_status(self, *, session: AsyncSession, order: Order, payment_status: str) -> Order:
        order.payment_status = payment_status
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

    async def count_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        query: ProfileOrderListQueryParams | OrderMyListQueryParams | None = None,
    ) -> int:
        statement = select(func.count(Order.id)).where(Order.user_id == user_id)
        statement = self._apply_filters(statement, query=query)
        result = await session.execute(statement)
        return int(result.scalar_one())

    async def get_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        query: ProfileOrderListQueryParams | OrderMyListQueryParams,
    ) -> list[ProfileOrderShortResponse | OrderShortResponse]:
        statement = select(Order).where(Order.user_id == user_id)
        statement = self._apply_filters(statement, query=query)
        statement = statement.order_by(desc(Order.created_date)).limit(query.limit).offset(query.offset)
        result = await session.execute(statement)
        if isinstance(query, OrderMyListQueryParams):
            return [self._build_my_order_response(order) for order in result.scalars().all()]
        return [self._build_order_response(order) for order in result.scalars().all()]

    async def get_recent_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        limit: int = 5,
    ) -> list[ProfileOrderShortResponse]:
        statement = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(desc(Order.created_date))
            .limit(limit)
        )
        result = await session.execute(statement)
        return [self._build_order_response(order) for order in result.scalars().all()]

    async def get_active_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> ProfileOrderShortResponse | None:
        result = await session.execute(
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES),
            )
            .order_by(desc(Order.created_date))
            .limit(1),
        )
        order = result.scalar_one_or_none()
        return self._build_order_response(order) if order is not None else None

    async def has_active_orders_by_address_id(
        self,
        *,
        session: AsyncSession,
        address_id: int,
    ) -> bool:
        result = await session.execute(
            select(Order.id)
            .where(
                Order.address_id == address_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES),
            )
            .limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def count_orders_by_time_slot(
        self,
        *,
        session: AsyncSession,
        delivery_date: date,
        delivery_time_slot_id: int,
        delivery_type: str,
        pickup_point_id: int | None = None,
    ) -> int:
        statement = select(func.count(Order.id)).where(
            Order.delivery_date == delivery_date,
            Order.delivery_time_slot_id == delivery_time_slot_id,
            Order.delivery_type == delivery_type,
            Order.status.in_(ACTIVE_ORDER_STATUSES),
        )
        if pickup_point_id is not None:
            statement = statement.where(Order.pickup_point_id == pickup_point_id)
        result = await session.execute(statement)
        return int(result.scalar_one())

    def _apply_filters(self, statement, *, query: ProfileOrderListQueryParams | OrderMyListQueryParams | None):
        if query is None:
            return statement
        if query.status is not None:
            statement = statement.where(Order.status == query.status)
        if query.payment_status is not None:
            statement = statement.where(Order.payment_status == query.payment_status)
        if query.delivery_type is not None:
            statement = statement.where(Order.delivery_type == query.delivery_type)
        if query.date_from is not None:
            statement = statement.where(Order.created_date >= datetime.combine(query.date_from, time.min))
        if query.date_to is not None:
            statement = statement.where(Order.created_date <= datetime.combine(query.date_to, time.max))
        return statement

    def _build_order_response(self, order: Order) -> ProfileOrderShortResponse:
        return ProfileOrderShortResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            final_price=order.final_price,
            items_count=order.items_count,
            created_at=order.created_date,
        )

    def _build_my_order_response(self, order: Order) -> OrderShortResponse:
        return OrderShortResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            final_price=order.final_price,
            items_count=order.items_count,
            created_at=order.created_date,
        )
