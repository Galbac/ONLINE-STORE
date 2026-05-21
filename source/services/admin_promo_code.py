from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError
from decimal import Decimal

from source.errors.promo_code import (
    EmptyPromoCodeUpdateError,
    PromoCodeAlreadyExistsError,
    PromoCodeNotFoundError,
    PromoCodeUsageLimitExceededError,
)
from source.schemas.pydantic.promo_code import (
    AdminPromoCodeCategoryResponse,
    AdminPromoCodeCreateRequest,
    AdminPromoCodeDetailResponse,
    AdminPromoCodeListItemResponse,
    AdminPromoCodeListQueryParams,
    AdminPromoCodeListResponse,
    AdminPromoCodeProductResponse,
    AdminPromoCodeUpdateRequest,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminPromoCodeService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:promo_codes:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:promo_codes:create" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:promo_codes:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_promo_codes(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminPromoCodeListQueryParams,
        permission_service,
        promo_code_repository,
        promo_code_usage_repository,
    ) -> AdminPromoCodeListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        cache_key = self._list_key(query_hash=build_query_hash(normalized_query.model_dump()))
        cached_promo_codes = await redis_service.get(cache_key)
        if cached_promo_codes is not None:
            if isinstance(cached_promo_codes, bytes):
                cached_promo_codes = cached_promo_codes.decode("utf-8")
            return AdminPromoCodeListResponse.model_validate_json(cached_promo_codes)

        promo_codes = await promo_code_repository.admin_get_list(session=session, query=normalized_query)
        total = await promo_code_repository.admin_count(session=session, query=normalized_query)
        usage_counts = await promo_code_usage_repository.count_grouped_by_promo_code_ids(
            session=session,
            promo_code_ids=[promo_code.id for promo_code in promo_codes],
        )
        response = AdminPromoCodeListResponse.build(
            items=[
                self._build_promo_code_response(
                    promo_code=promo_code,
                    usage_count=usage_counts.get(promo_code.id, 0),
                )
                for promo_code in promo_codes
            ],
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.promo_codes.admin_list_cache_ttl_seconds,
        )
        return response

    async def get_promo_code_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        promo_code_id: int,
        permission_service,
        promo_code_repository,
        promo_code_usage_repository,
        promo_code_product_repository,
        promo_code_category_repository,
    ) -> AdminPromoCodeDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cache_key = self._detail_key(promo_code_id=promo_code_id)
        cached_promo_code = await redis_service.get(cache_key)
        if cached_promo_code is not None:
            if isinstance(cached_promo_code, bytes):
                cached_promo_code = cached_promo_code.decode("utf-8")
            return AdminPromoCodeDetailResponse.model_validate_json(cached_promo_code)

        promo_code = await promo_code_repository.admin_get_by_id(session=session, promo_code_id=promo_code_id)
        if promo_code is None:
            raise PromoCodeNotFoundError

        usage_count = await promo_code_usage_repository.count_by_promo_code_id(
            session=session,
            promo_code_id=promo_code.id,
        )
        products = await promo_code_product_repository.get_products(session=session, promo_code_id=promo_code.id)
        categories = await promo_code_category_repository.get_categories(session=session, promo_code_id=promo_code.id)
        response = self._build_detail_response(
            promo_code=promo_code,
            usage_count=usage_count,
            products=products,
            categories=categories,
        )
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.promo_codes.admin_detail_cache_ttl_seconds,
        )
        return response

    async def create_promo_code(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminPromoCodeCreateRequest,
        commiter,
        permission_service,
        promo_code_repository,
        promo_code_product_repository,
        promo_code_category_repository,
        product_repository,
        category_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminPromoCodeDetailResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        existing_promo_code = await promo_code_repository.get_by_code(session=session, code=data.code)
        if existing_promo_code is not None:
            raise PromoCodeAlreadyExistsError

        if data.product_ids:
            products = await product_repository.get_by_ids(session=session, product_ids=data.product_ids)
            if len({product.id for product in products}) != len(set(data.product_ids)):
                raise ProductNotFoundError
        if data.category_ids:
            categories = await category_repository.get_by_ids(session=session, category_ids=data.category_ids)
            if len({category.id for category in categories}) != len(set(data.category_ids)):
                raise CategoryNotFoundError

        created_promo_code = await promo_code_repository.create(
            session=session,
            code=data.code,
            name=data.name,
            description=data.description,
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            min_order_amount=data.min_order_amount,
            max_discount_amount=data.max_discount_amount,
            usage_limit=data.usage_limit,
            per_user_usage_limit=data.user_usage_limit,
            applicable_product_id=data.product_ids[0] if data.product_ids else None,
            applicable_category_id=data.category_ids[0] if data.category_ids else None,
            is_active=data.is_active,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
        )
        if data.product_ids:
            await promo_code_product_repository.bulk_create(
                session=session,
                promo_code_id=created_promo_code.id,
                product_ids=data.product_ids,
            )
        if data.category_ids:
            await promo_code_category_repository.bulk_create(
                session=session,
                promo_code_id=created_promo_code.id,
                category_ids=data.category_ids,
            )

        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_promo_code_create",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "promo_code_id": created_promo_code.id,
                "code": created_promo_code.code,
                "discount_type": created_promo_code.discount_type,
                "product_ids": data.product_ids,
                "category_ids": data.category_ids,
            },
        )
        await commiter.commit()

        await redis_service.delete_by_pattern("admin:promo_codes:*")

        return self._build_detail_response(promo_code=created_promo_code)

    async def update_promo_code(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        promo_code_id: int,
        data: AdminPromoCodeUpdateRequest,
        commiter,
        permission_service,
        promo_code_repository,
        promo_code_usage_repository,
        promo_code_product_repository,
        promo_code_category_repository,
        product_repository,
        category_repository,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminPromoCodeDetailResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyPromoCodeUpdateError

        promo_code = await promo_code_repository.admin_get_by_id(session=session, promo_code_id=promo_code_id)
        if promo_code is None:
            raise PromoCodeNotFoundError

        new_code = update_fields.get("code")
        if new_code is not None and new_code != promo_code.code:
            existing_promo_code = await promo_code_repository.get_by_code(session=session, code=new_code)
            if existing_promo_code is not None:
                raise PromoCodeAlreadyExistsError

        next_discount_type = update_fields.get("discount_type", promo_code.discount_type)
        next_discount_value = update_fields.get("discount_value", promo_code.discount_value)
        if next_discount_type == "percent" and not Decimal("1") <= next_discount_value <= Decimal("100"):
            raise ValueError("percent discount_value must be between 1 and 100")

        next_starts_at = update_fields.get("starts_at", promo_code.starts_at)
        next_ends_at = update_fields.get("ends_at", promo_code.ends_at)
        if next_starts_at is not None and next_ends_at is not None and next_starts_at >= next_ends_at:
            raise ValueError("starts_at must be less than ends_at")

        usage_count = await promo_code_usage_repository.count_by_promo_code_id(
            session=session,
            promo_code_id=promo_code.id,
        )
        if update_fields.get("usage_limit") is not None and update_fields["usage_limit"] < usage_count:
            raise PromoCodeUsageLimitExceededError

        product_ids = update_fields.pop("product_ids", None)
        category_ids = update_fields.pop("category_ids", None)
        if product_ids is not None:
            products = await product_repository.get_by_ids(session=session, product_ids=product_ids)
            if len({product.id for product in products}) != len(set(product_ids)):
                raise ProductNotFoundError
        if category_ids is not None:
            categories = await category_repository.get_by_ids(session=session, category_ids=category_ids)
            if len({category.id for category in categories}) != len(set(category_ids)):
                raise CategoryNotFoundError

        repository_data = {
            **update_fields,
        }
        if product_ids is not None:
            repository_data["applicable_product_id"] = product_ids[0] if product_ids else None
        if category_ids is not None:
            repository_data["applicable_category_id"] = category_ids[0] if category_ids else None
        if "user_usage_limit" in repository_data:
            repository_data["per_user_usage_limit"] = repository_data.pop("user_usage_limit")

        before = {
            field: getattr(promo_code, field)
            for field in repository_data
        }
        updated_promo_code = await promo_code_repository.update(
            session=session,
            promo_code=promo_code,
            data=repository_data,
        )
        if product_ids is not None:
            await promo_code_product_repository.replace_products(
                session=session,
                promo_code_id=updated_promo_code.id,
                product_ids=product_ids,
            )
        if category_ids is not None:
            await promo_code_category_repository.replace_categories(
                session=session,
                promo_code_id=updated_promo_code.id,
                category_ids=category_ids,
            )

        products = await promo_code_product_repository.get_products(session=session, promo_code_id=updated_promo_code.id)
        categories = await promo_code_category_repository.get_categories(session=session, promo_code_id=updated_promo_code.id)
        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_promo_code, field)) if getattr(updated_promo_code, field) is not None else None,
            }
            for field in repository_data
            if before[field] != getattr(updated_promo_code, field)
        }
        if product_ids is not None:
            changes["product_ids"] = {"new": product_ids}
        if category_ids is not None:
            changes["category_ids"] = {"new": category_ids}

        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_promo_code_update",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "promo_code_id": updated_promo_code.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await redis_service.delete_by_pattern("admin:promo_codes:*")
        await redis_service.delete_by_pattern("cart:*")

        return self._build_detail_response(
            promo_code=updated_promo_code,
            usage_count=usage_count,
            products=products,
            categories=categories,
        )

    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:promo_codes:list:{query_hash}"

    def _detail_key(self, *, promo_code_id: int) -> str:
        return f"admin:promo_codes:detail:{promo_code_id}"

    def _build_promo_code_response(self, *, promo_code, usage_count: int) -> AdminPromoCodeListItemResponse:
        return AdminPromoCodeListItemResponse(
            id=promo_code.id,
            code=promo_code.code,
            name=getattr(promo_code, "name", None),
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            min_order_amount=promo_code.min_order_amount,
            usage_limit=promo_code.usage_limit,
            usage_count=usage_count,
            user_usage_limit=promo_code.per_user_usage_limit,
            is_active=promo_code.is_active,
            starts_at=promo_code.starts_at,
            ends_at=promo_code.ends_at,
        )

    def _build_detail_response(
        self,
        *,
        promo_code,
        usage_count: int = 0,
        products=None,
        categories=None,
    ) -> AdminPromoCodeDetailResponse:
        return AdminPromoCodeDetailResponse(
            id=promo_code.id,
            code=promo_code.code,
            name=getattr(promo_code, "name", None),
            description=getattr(promo_code, "description", None),
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            min_order_amount=promo_code.min_order_amount,
            max_discount_amount=getattr(promo_code, "max_discount_amount", None),
            usage_limit=promo_code.usage_limit,
            usage_count=usage_count,
            user_usage_limit=promo_code.per_user_usage_limit,
            starts_at=promo_code.starts_at,
            ends_at=promo_code.ends_at,
            is_active=promo_code.is_active,
            updated_at=getattr(promo_code, "updated_date", None),
            products=[
                AdminPromoCodeProductResponse(
                    id=product.id,
                    name=product.name,
                    price=product.price,
                )
                for product in products or []
            ],
            categories=[
                AdminPromoCodeCategoryResponse(
                    id=category.id,
                    name=category.name,
                )
                for category in categories or []
            ],
        )
