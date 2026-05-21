from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError
from source.schemas.pydantic.discount import (
    AdminDiscountCreateRequest,
    AdminDiscountDetailResponse,
    AdminDiscountListItemResponse,
    AdminDiscountListQueryParams,
    AdminDiscountListResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class DiscountConflictService:
    async def check_conflicts(self, **kwargs) -> None:
        return None


class AdminDiscountService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:discounts:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:discounts:create" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_discounts(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminDiscountListQueryParams,
        permission_service,
        discount_repository,
        admin_discount_cache_service,
    ) -> AdminDiscountListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_discounts = await admin_discount_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_discounts is not None:
            return cached_discounts

        discounts = await discount_repository.admin_get_list(session=session, query=normalized_query)
        total = await discount_repository.admin_count(session=session, query=normalized_query)
        response = AdminDiscountListResponse.build(
            items=[self._build_discount_response(discount=discount) for discount in discounts],
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_discount_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.discounts.admin_list_cache_ttl_seconds,
        )
        return response

    def _build_discount_response(self, *, discount) -> AdminDiscountListItemResponse:
        return AdminDiscountListItemResponse(
            id=discount.id,
            name=discount.name,
            type=discount.type,
            discount_type=discount.discount_type,
            discount_value=discount.discount_value,
            is_active=discount.is_active,
            starts_at=discount.starts_at,
            ends_at=discount.ends_at,
            created_at=discount.created_date,
        )

    async def create_discount(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminDiscountCreateRequest,
        commiter,
        permission_service,
        discount_repository,
        discount_product_repository,
        discount_category_repository,
        product_repository,
        category_repository,
        discount_conflict_service,
        audit_log_service,
        admin_audit_log_repository,
        admin_discount_cache_service,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminDiscountDetailResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        product_ids = data.product_ids or []
        category_ids = data.category_ids or []
        if data.type == "product":
            products = await product_repository.get_by_ids(session=session, product_ids=product_ids)
            if len({product.id for product in products}) != len(set(product_ids)):
                raise ProductNotFoundError
        if data.type == "category":
            categories = await category_repository.get_by_ids(session=session, category_ids=category_ids)
            if len({category.id for category in categories}) != len(set(category_ids)):
                raise CategoryNotFoundError

        await discount_conflict_service.check_conflicts(session=session, data=data)

        created_discount = await discount_repository.create(
            session=session,
            name=data.name,
            type=data.type,
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            applicable_product_id=product_ids[0] if product_ids else None,
            applicable_category_id=category_ids[0] if category_ids else None,
            is_active=data.is_active,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
        )
        if product_ids:
            await discount_product_repository.bulk_create(
                session=session,
                discount_id=created_discount.id,
                product_ids=product_ids,
            )
        if category_ids:
            await discount_category_repository.bulk_create(
                session=session,
                discount_id=created_discount.id,
                category_ids=category_ids,
            )

        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_discount_create",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "discount_id": created_discount.id,
                "type": created_discount.type,
                "discount_type": created_discount.discount_type,
                "product_ids": product_ids,
                "category_ids": category_ids,
            },
        )
        await commiter.commit()

        await self._invalidate_discount_cache(
            redis_service=redis_service,
            admin_discount_cache_service=admin_discount_cache_service,
        )

        return self._build_discount_detail_response(discount=created_discount)

    async def _invalidate_discount_cache(self, *, redis_service: RedisService, admin_discount_cache_service) -> None:
        await admin_discount_cache_service.invalidate_all(redis_service=redis_service)
        await redis_service.delete_by_pattern("discounts:*")
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:detail:*")
        await redis_service.delete_by_pattern("products:slug:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("cart:*")

    def _build_discount_detail_response(self, *, discount) -> AdminDiscountDetailResponse:
        return AdminDiscountDetailResponse(
            id=discount.id,
            name=discount.name,
            type=discount.type,
            discount_type=discount.discount_type,
            discount_value=discount.discount_value,
            is_active=discount.is_active,
            starts_at=discount.starts_at,
            ends_at=discount.ends_at,
        )
