from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.integration_log import IntegrationLog
from source.schemas.pydantic.one_c import AdminOneCLogsQueryParams


ONE_C_LOG_ENTITY_TYPE_MAP = {
    "categories": ("categories",),
    "products": ("products",),
    "prices": ("prices", "product_prices"),
    "stocks": ("stocks", "product_stocks"),
    "images": ("images", "product_images"),
    "orders": ("orders", "order"),
}

ONE_C_LOG_INBOUND_ENTITY_TYPES = ("categories", "products", "prices", "product_prices", "stocks", "product_stocks", "images", "product_images")
ONE_C_LOG_OUTBOUND_ENTITY_TYPES = ("orders", "order")


class IntegrationLogRepository:
    async def create(self, *, session: AsyncSession, **data) -> IntegrationLog:
        log = IntegrationLog(**data)
        session.add(log)
        await session.flush()
        await session.refresh(log)
        return log

    async def get_list(self, *, session: AsyncSession, query: AdminOneCLogsQueryParams) -> list[IntegrationLog]:
        statement = self._build_query(query=query)
        statement = statement.order_by(IntegrationLog.created_date.desc(), IntegrationLog.id.desc())
        statement = statement.offset((query.page - 1) * query.limit).limit(query.limit)
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def count(self, *, session: AsyncSession, query: AdminOneCLogsQueryParams) -> int:
        statement = self._build_query(query=query, count=True)
        result = await session.execute(statement)
        return int(result.scalar_one() or 0)

    def _build_query(self, *, query: AdminOneCLogsQueryParams, count: bool = False):
        statement = select(func.count(IntegrationLog.id)) if count else select(IntegrationLog)
        statement = statement.where(IntegrationLog.system == "1c")

        if query.direction == "inbound":
            statement = statement.where(IntegrationLog.entity_type.in_(ONE_C_LOG_INBOUND_ENTITY_TYPES))
        elif query.direction == "outbound":
            statement = statement.where(IntegrationLog.entity_type.in_(ONE_C_LOG_OUTBOUND_ENTITY_TYPES))

        if query.entity_type is not None:
            statement = statement.where(IntegrationLog.entity_type.in_(ONE_C_LOG_ENTITY_TYPE_MAP[query.entity_type]))
        if query.status is not None:
            statement = statement.where(IntegrationLog.status == query.status)
        if query.date_from is not None:
            statement = statement.where(IntegrationLog.created_date >= query.date_from)
        if query.date_to is not None:
            statement = statement.where(IntegrationLog.created_date <= query.date_to)
        if query.q is not None:
            search = f"%{query.q.lower()}%"
            statement = statement.where(
                or_(
                    func.lower(IntegrationLog.action).like(search),
                    func.lower(IntegrationLog.error_message).like(search),
                    cast(IntegrationLog.entity_id, String).like(search),
                    func.lower(cast(IntegrationLog.request_payload, String)).like(search),
                    func.lower(cast(IntegrationLog.response_payload, String)).like(search),
                ),
            )
        return statement
