from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.admin_dashboard import (
    AdminDashboardOrdersStats,
    AdminDashboardProductsStats,
    AdminDashboardResponse,
    AdminDashboardSalesStats,
    AdminDashboardUsersStats,
    AdminLowStockQueryParams,
    AdminLowStockResponse,
    AdminSalesQueryParams,
    AdminSalesResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash


class AdminDashboardService:
    async def get_summary(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        permission_service,
        order_repository,
        product_repository,
        user_repository,
        admin_dashboard_cache_service,
    ) -> AdminDashboardResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:dashboard:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

        cached_summary = await admin_dashboard_cache_service.get_summary(redis_service=redis_service)
        if cached_summary is not None:
            return cached_summary

        orders_stats = await order_repository.get_dashboard_stats(session=session)
        low_stock_count = await product_repository.count_low_stock(session=session)
        total_active_products = await product_repository.count_total_active(session=session)
        users_count = await user_repository.count_customers(session=session)
        recent_orders = await order_repository.get_dashboard_recent_orders(session=session, limit=5)
        popular_products = await product_repository.get_dashboard_popular_products(session=session, limit=5)

        response = AdminDashboardResponse(
            orders=AdminDashboardOrdersStats(
                today_count=orders_stats.today_count,
                new_count=orders_stats.new_count,
                paid_today_count=orders_stats.paid_today_count,
            ),
            sales=AdminDashboardSalesStats(
                today_amount=orders_stats.sales_today_amount,
                currency=settings.payments.currency,
            ),
            products=AdminDashboardProductsStats(
                low_stock_count=low_stock_count,
                total_active=total_active_products,
            ),
            users=AdminDashboardUsersStats(total=users_count),
            recent_orders=recent_orders,
            popular_products=popular_products,
        )
        await admin_dashboard_cache_service.set_summary(
            redis_service=redis_service,
            response=response,
            ttl_seconds=settings.admin_dashboard.cache_ttl_seconds,
        )
        return response

    async def get_sales(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminSalesQueryParams,
        permission_service,
        order_repository,
        admin_dashboard_cache_service,
    ) -> AdminSalesResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:dashboard:sales:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

        query_hash = build_query_hash(query.model_dump())
        cached_sales = await admin_dashboard_cache_service.get_sales(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_sales is not None:
            return cached_sales

        response = await order_repository.get_sales_stats(session=session, query=query)
        await admin_dashboard_cache_service.set_sales(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.admin_dashboard.sales_cache_ttl_seconds,
        )
        return response

    async def get_low_stock_products(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminLowStockQueryParams,
        permission_service,
        product_repository,
        admin_dashboard_cache_service,
    ) -> AdminLowStockResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:products:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

        query_hash = build_query_hash(query.model_dump())
        cached_low_stock = await admin_dashboard_cache_service.get_low_stock(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_low_stock is not None:
            return cached_low_stock

        items = await product_repository.get_low_stock(session=session, query=query)
        total = await product_repository.count_low_stock(session=session, category_id=query.category_id)
        response = AdminLowStockResponse(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
        )
        await admin_dashboard_cache_service.set_low_stock(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.admin_dashboard.low_stock_cache_ttl_seconds,
        )
        return response
