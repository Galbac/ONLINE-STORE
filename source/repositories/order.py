from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import cast, Date, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.order import Order
from source.schemas.pydantic.order import AdminOrderListItemResponse, AdminOrderListQueryParams, OrderMyListQueryParams, OrderShortResponse
from source.schemas.pydantic.admin_dashboard import AdminRecentOrderResponse, AdminSalesQueryParams, AdminSalesResponse, AdminSalesSeriesItem
from source.schemas.pydantic.profile import ProfileOrderListQueryParams, ProfileOrderShortResponse
from source.schemas.pydantic.user import AdminUserOrdersQueryParams


ACTIVE_ORDER_STATUSES = ("new", "paid", "assembling", "delivering", "in_progress")
DELIVERY_ZONE_ACTIVE_ORDER_STATUSES = ("new", "confirmed", "assembling", "delivering", "pending_payment")
PICKUP_POINT_ACTIVE_ORDER_STATUSES = ("new", "confirmed", "assembling", "ready_for_pickup")
PENDING_1C_SYNC_STATUSES = ("pending", "pending_update", "pending_cancel")
EXCLUDED_1C_ORDER_STATUSES = ("draft", "pending_payment")


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

    async def get_pending_sync(
        self,
        *,
        session: AsyncSession,
        limit: int,
        sync_status: str | None = None,
    ) -> list[Order]:
        sync_statuses = (sync_status,) if sync_status is not None else PENDING_1C_SYNC_STATUSES
        result = await session.execute(
            select(Order)
            .where(
                Order.sync_status.in_(sync_statuses),
                Order.status.notin_(EXCLUDED_1C_ORDER_STATUSES),
            )
            .order_by(Order.created_date.asc(), Order.id.asc())
            .limit(limit),
        )
        return list(result.scalars().all())

    async def exists_active_by_delivery_zone_id(
        self,
        *,
        session: AsyncSession,
        delivery_zone_id: int,
    ) -> bool:
        result = await session.execute(
            select(Order.id)
            .where(
                Order.delivery_zone_id == delivery_zone_id,
                Order.status.in_(DELIVERY_ZONE_ACTIVE_ORDER_STATUSES),
            )
            .limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def exists_active_by_pickup_point_id(
        self,
        *,
        session: AsyncSession,
        pickup_point_id: int,
    ) -> bool:
        result = await session.execute(
            select(Order.id)
            .where(
                Order.pickup_point_id == pickup_point_id,
                Order.status.in_(PICKUP_POINT_ACTIVE_ORDER_STATUSES),
            )
            .limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def admin_get_by_id(
        self,
        *,
        session: AsyncSession,
        order_id: int,
    ) -> Order | None:
        return await self.get_by_id(session=session, order_id=order_id)

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

    async def get_sales_stats(
        self,
        *,
        session: AsyncSession,
        query: AdminSalesQueryParams,
    ) -> AdminSalesResponse:
        period_expression = cast(func.date_trunc(query.group_by, Order.created_date), Date)
        statement = (
            select(
                period_expression.label("period"),
                func.coalesce(func.sum(Order.final_price), 0),
                func.count(Order.id),
            )
            .where(
                Order.created_date >= datetime.combine(query.date_from, time.min),
                Order.created_date <= datetime.combine(query.date_to, time.max),
                Order.status != "cancelled",
                or_(
                    Order.payment_status == "paid",
                    Order.status == "completed",
                ),
            )
            .group_by(period_expression)
            .order_by(period_expression.asc())
        )
        result = await session.execute(statement)
        series = [
            AdminSalesSeriesItem(
                date=period,
                amount=Decimal(str(amount)),
                orders_count=int(orders_count),
            )
            for period, amount, orders_count in result.all()
        ]
        total_amount = sum((item.amount for item in series), Decimal("0.00"))
        orders_count = sum(item.orders_count for item in series)
        average_order_value = total_amount / orders_count if orders_count else Decimal("0.00")
        return AdminSalesResponse(
            date_from=query.date_from,
            date_to=query.date_to,
            group_by=query.group_by,
            total_amount=total_amount,
            orders_count=orders_count,
            average_order_value=average_order_value,
            series=series,
        )

    async def get_status_by_id(self, *, session: AsyncSession, order_id: int) -> Order | None:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def update_status(self, *, session: AsyncSession, order: Order, status: str, sync_status: str | None = None) -> Order:
        order.status = status
        if sync_status is not None:
            order.sync_status = sync_status
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

    async def update_allowed_fields(self, *, session: AsyncSession, order: Order, data: dict) -> Order:
        for field, value in data.items():
            setattr(order, field, value)
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

    async def update_sync_status(
        self,
        *,
        session: AsyncSession,
        order: Order,
        sync_status: str,
        external_1c_id: str | None = None,
        sync_error: str | None = None,
        sync_error_code: str | None = None,
        last_sync_at=None,
    ) -> Order:
        order.sync_status = sync_status
        order.external_1c_id = external_1c_id
        order.sync_error = sync_error
        order.sync_error_code = sync_error_code
        order.last_sync_at = last_sync_at
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

    async def update_sync_success(
        self,
        *,
        session: AsyncSession,
        order: Order,
        external_1c_id: str | None,
        last_sync_at,
    ) -> Order:
        return await self.update_sync_status(
            session=session,
            order=order,
            sync_status="synced",
            external_1c_id=external_1c_id,
            sync_error=None,
            last_sync_at=last_sync_at,
        )

    async def update_sync_error(
        self,
        *,
        session: AsyncSession,
        order: Order,
        sync_error: str,
        sync_error_code: str | None,
        last_sync_at,
    ) -> Order:
        return await self.update_sync_status(
            session=session,
            order=order,
            sync_status="error",
            external_1c_id=order.external_1c_id,
            sync_error=sync_error,
            sync_error_code=sync_error_code,
            last_sync_at=last_sync_at,
        )

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
        query: ProfileOrderListQueryParams | OrderMyListQueryParams | AdminUserOrdersQueryParams | None = None,
    ) -> int:
        statement = select(func.count(Order.id)).where(Order.user_id == user_id)
        statement = self._apply_filters(statement, query=query)
        result = await session.execute(statement)
        return int(result.scalar_one())

    async def admin_get_list(
        self,
        *,
        session: AsyncSession,
        query: AdminOrderListQueryParams,
    ) -> list[AdminOrderListItemResponse]:
        statement = self._apply_admin_filters(select(Order), query=query)
        result = await session.execute(
            statement.order_by(desc(Order.created_date)).limit(query.limit).offset(query.offset),
        )
        return [self._build_admin_order_response(order) for order in result.scalars().all()]

    async def admin_count(self, *, session: AsyncSession, query: AdminOrderListQueryParams) -> int:
        statement = self._apply_admin_filters(select(Order.id), query=query).subquery()
        result = await session.execute(select(func.count()).select_from(statement))
        return int(result.scalar_one())

    async def get_user_stats_grouped(
        self,
        *,
        session: AsyncSession,
        user_ids: list[int],
    ) -> dict[int, SimpleNamespace]:
        if not user_ids:
            return {}
        result = await session.execute(
            select(
                Order.user_id,
                func.count(Order.id).filter(Order.status != "cancelled"),
                func.coalesce(
                    func.sum(Order.final_price).filter(
                        Order.status != "cancelled",
                        or_(
                            Order.payment_status == "paid",
                            Order.status == "completed",
                        ),
                    ),
                    0,
                ),
            )
            .where(Order.user_id.in_(user_ids))
            .group_by(Order.user_id),
        )
        return {
            int(user_id): SimpleNamespace(
                orders_count=int(orders_count),
                total_spent=Decimal(str(total_spent)),
            )
            for user_id, orders_count, total_spent in result.all()
        }

    async def get_user_stats(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> SimpleNamespace:
        result = await session.execute(
            select(
                func.count(Order.id).filter(Order.status != "cancelled"),
                func.coalesce(
                    func.sum(Order.final_price).filter(
                        Order.status != "cancelled",
                        or_(
                            Order.payment_status == "paid",
                            Order.status == "completed",
                        ),
                    ),
                    0,
                ),
            ).where(Order.user_id == user_id),
        )
        orders_count, total_spent = result.one()
        return SimpleNamespace(
            orders_count=int(orders_count),
            total_spent=Decimal(str(total_spent)),
        )

    async def get_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        query: ProfileOrderListQueryParams | OrderMyListQueryParams | AdminUserOrdersQueryParams,
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

    def _apply_filters(self, statement, *, query: ProfileOrderListQueryParams | OrderMyListQueryParams | AdminUserOrdersQueryParams | None):
        if query is None:
            return statement
        if query.status is not None:
            statement = statement.where(Order.status == query.status)
        if query.payment_status is not None:
            statement = statement.where(Order.payment_status == query.payment_status)
        delivery_type = getattr(query, "delivery_type", None)
        if delivery_type is not None:
            statement = statement.where(Order.delivery_type == delivery_type)
        if query.date_from is not None:
            statement = statement.where(Order.created_date >= datetime.combine(query.date_from, time.min))
        if query.date_to is not None:
            statement = statement.where(Order.created_date <= datetime.combine(query.date_to, time.max))
        return statement

    def _apply_admin_filters(self, statement, *, query: AdminOrderListQueryParams):
        if query.q is not None:
            search = f"%{query.q}%"
            statement = statement.where(
                or_(
                    Order.order_number.ilike(search),
                    Order.customer_phone.ilike(search),
                    Order.customer_email.ilike(search),
                    Order.customer_name.ilike(search),
                ),
            )
        if query.status is not None:
            statement = statement.where(Order.status == query.status)
        if query.payment_status is not None:
            statement = statement.where(Order.payment_status == query.payment_status)
        if query.payment_method is not None:
            statement = statement.where(Order.payment_method == query.payment_method)
        if query.delivery_type is not None:
            statement = statement.where(Order.delivery_type == query.delivery_type)
        if query.sync_status is not None:
            statement = statement.where(Order.sync_status == query.sync_status)
        if query.date_from is not None:
            statement = statement.where(Order.created_date >= datetime.combine(query.date_from, time.min))
        if query.date_to is not None:
            statement = statement.where(Order.created_date <= datetime.combine(query.date_to, time.max))
        if query.min_amount is not None:
            statement = statement.where(Order.final_price >= query.min_amount)
        if query.max_amount is not None:
            statement = statement.where(Order.final_price <= query.max_amount)
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

    def _build_admin_order_response(self, order: Order) -> AdminOrderListItemResponse:
        return AdminOrderListItemResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            final_price=order.final_price,
            sync_status=order.sync_status,
            created_at=order.created_date,
        )
