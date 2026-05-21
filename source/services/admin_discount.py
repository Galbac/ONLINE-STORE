from decimal import Decimal

from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.category import CategoryNotFoundError
from source.errors.discount import DiscountConflictError, DiscountNotFoundError, EmptyDiscountUpdateError
from source.errors.product import ProductNotFoundError
from source.schemas.pydantic.discount import (
    AdminDiscountCreateRequest,
    AdminDiscountCategoryResponse,
    AdminDiscountDetailResponse,
    AdminDiscountListItemResponse,
    AdminDiscountListQueryParams,
    AdminDiscountListResponse,
    AdminDiscountProductResponse,
    AdminDiscountUpdateRequest,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class DiscountConflictService:
    async def check_conflicts(
        self,
        *,
        session,
        discount_repository=None,
        data=None,
        discount_id: int | None = None,
        type: str | None = None,
        product_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
        starts_at=None,
        ends_at=None,
        is_active: bool = True,
    ) -> None:
        if discount_repository is None:
            return

        conflict_type = type or getattr(data, "type", None)
        if conflict_type is None:
            return

        has_conflicts = await discount_repository.has_conflicts(
            session=session,
            discount_id=discount_id,
            type=conflict_type,
            product_ids=product_ids if product_ids is not None else getattr(data, "product_ids", None) or [],
            category_ids=category_ids if category_ids is not None else getattr(data, "category_ids", None) or [],
            starts_at=starts_at if starts_at is not None else getattr(data, "starts_at", None),
            ends_at=ends_at if ends_at is not None else getattr(data, "ends_at", None),
            is_active=is_active if is_active is not None else getattr(data, "is_active", True),
        )
        if has_conflicts:
            raise DiscountConflictError


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

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:discounts:update" not in permission_service.get_user_permissions(role=user.role):
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

    async def get_discount_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        discount_id: int,
        permission_service,
        discount_repository,
        discount_product_repository,
        discount_category_repository,
        admin_discount_cache_service,
    ) -> AdminDiscountDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_discount = await admin_discount_cache_service.get_detail(
            redis_service=redis_service,
            discount_id=discount_id,
        )
        if cached_discount is not None:
            return cached_discount

        discount = await discount_repository.admin_get_by_id(session=session, discount_id=discount_id)
        if discount is None:
            raise DiscountNotFoundError

        products = await discount_product_repository.get_products(session=session, discount_id=discount.id)
        categories = await discount_category_repository.get_categories(session=session, discount_id=discount.id)
        response = self._build_discount_detail_response(
            discount=discount,
            products=products,
            categories=categories,
        )
        await admin_discount_cache_service.set_detail(
            redis_service=redis_service,
            discount_id=discount.id,
            response=response,
            ttl_seconds=settings.discounts.admin_detail_cache_ttl_seconds,
        )
        return response

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

        await discount_conflict_service.check_conflicts(
            session=session,
            discount_repository=discount_repository,
            data=data,
        )

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

    async def update_discount(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        discount_id: int,
        data: AdminDiscountUpdateRequest,
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
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyDiscountUpdateError

        discount = await discount_repository.admin_get_by_id(session=session, discount_id=discount_id)
        if discount is None:
            raise DiscountNotFoundError

        old_products = await discount_product_repository.get_products(session=session, discount_id=discount.id)
        old_categories = await discount_category_repository.get_categories(session=session, discount_id=discount.id)
        current_product_ids = [product.id for product in old_products]
        current_category_ids = [category.id for category in old_categories]

        product_ids = update_fields.pop("product_ids", None)
        category_ids = update_fields.pop("category_ids", None)
        next_product_ids = product_ids if product_ids is not None else current_product_ids
        next_category_ids = category_ids if category_ids is not None else current_category_ids

        if product_ids is not None:
            products = await product_repository.get_by_ids(session=session, product_ids=product_ids)
            if len({product.id for product in products}) != len(set(product_ids)):
                raise ProductNotFoundError
        if category_ids is not None:
            categories = await category_repository.get_by_ids(session=session, category_ids=category_ids)
            if len({category.id for category in categories}) != len(set(category_ids)):
                raise CategoryNotFoundError

        next_type = self._resolve_discount_type(
            current_type=discount.type,
            product_ids=product_ids,
            category_ids=category_ids,
            next_product_ids=next_product_ids,
            next_category_ids=next_category_ids,
        )
        if next_type == "product" and not next_product_ids:
            raise ValueError("product discount must contain product_ids")
        if next_type == "category" and not next_category_ids:
            raise ValueError("category discount must contain category_ids")
        if next_type == "cart":
            next_product_ids = []
            next_category_ids = []

        next_discount_type = update_fields.get("discount_type", discount.discount_type)
        next_discount_value = update_fields.get("discount_value", discount.discount_value)
        if next_discount_type == "percent" and not Decimal("1") <= next_discount_value <= Decimal("100"):
            raise ValueError("percent discount_value must be between 1 and 100")

        next_starts_at = update_fields.get("starts_at", discount.starts_at)
        next_ends_at = update_fields.get("ends_at", discount.ends_at)
        if next_starts_at is not None and next_ends_at is not None and next_starts_at >= next_ends_at:
            raise ValueError("starts_at must be less than ends_at")

        next_is_active = update_fields.get("is_active", discount.is_active)
        await discount_conflict_service.check_conflicts(
            session=session,
            discount_repository=discount_repository,
            discount_id=discount.id,
            type=next_type,
            product_ids=next_product_ids,
            category_ids=next_category_ids,
            starts_at=next_starts_at,
            ends_at=next_ends_at,
            is_active=next_is_active,
        )

        repository_data = {
            **update_fields,
            "type": next_type,
            "applicable_product_id": next_product_ids[0] if next_type == "product" and next_product_ids else None,
            "applicable_category_id": next_category_ids[0] if next_type == "category" and next_category_ids else None,
        }
        before = {
            field: getattr(discount, field)
            for field in repository_data
        }
        updated_discount = await discount_repository.update(
            session=session,
            discount=discount,
            data=repository_data,
        )
        if product_ids is not None or next_type != "product":
            await discount_product_repository.replace_products(
                session=session,
                discount_id=updated_discount.id,
                product_ids=next_product_ids if next_type == "product" else [],
            )
        if category_ids is not None or next_type != "category":
            await discount_category_repository.replace_categories(
                session=session,
                discount_id=updated_discount.id,
                category_ids=next_category_ids if next_type == "category" else [],
            )

        products = await discount_product_repository.get_products(session=session, discount_id=updated_discount.id)
        categories = await discount_category_repository.get_categories(session=session, discount_id=updated_discount.id)
        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_discount, field)) if getattr(updated_discount, field) is not None else None,
            }
            for field in repository_data
            if before[field] != getattr(updated_discount, field)
        }
        if product_ids is not None and current_product_ids != next_product_ids:
            changes["product_ids"] = {"old": current_product_ids, "new": next_product_ids}
        if category_ids is not None and current_category_ids != next_category_ids:
            changes["category_ids"] = {"old": current_category_ids, "new": next_category_ids}

        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_discount_update",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "discount_id": updated_discount.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await self._invalidate_discount_cache(
            redis_service=redis_service,
            admin_discount_cache_service=admin_discount_cache_service,
        )

        return self._build_discount_detail_response(
            discount=updated_discount,
            products=products,
            categories=categories,
        )

    def _resolve_discount_type(
        self,
        *,
        current_type: str,
        product_ids: list[int] | None,
        category_ids: list[int] | None,
        next_product_ids: list[int],
        next_category_ids: list[int],
    ) -> str:
        if product_ids is not None and product_ids:
            return "product"
        if category_ids is not None and category_ids:
            return "category"
        if product_ids == [] and category_ids == []:
            return "cart"
        if current_type == "product" and product_ids == []:
            return "cart" if not next_category_ids else "category"
        if current_type == "category" and category_ids == []:
            return "cart" if not next_product_ids else "product"
        return current_type

    async def _invalidate_discount_cache(self, *, redis_service: RedisService, admin_discount_cache_service) -> None:
        await admin_discount_cache_service.invalidate_all(redis_service=redis_service)
        await redis_service.delete_by_pattern("discounts:*")
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:detail:*")
        await redis_service.delete_by_pattern("products:slug:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("cart:*")

    def _build_discount_detail_response(
        self,
        *,
        discount,
        products=None,
        categories=None,
    ) -> AdminDiscountDetailResponse:
        return AdminDiscountDetailResponse(
            id=discount.id,
            name=discount.name,
            type=discount.type,
            discount_type=discount.discount_type,
            discount_value=discount.discount_value,
            is_active=discount.is_active,
            starts_at=discount.starts_at,
            ends_at=discount.ends_at,
            updated_at=getattr(discount, "updated_date", None),
            products=[
                AdminDiscountProductResponse(
                    id=product.id,
                    name=product.name,
                    price=product.price,
                )
                for product in products or []
            ],
            categories=[
                AdminDiscountCategoryResponse(
                    id=category.id,
                    name=category.name,
                )
                for category in categories or []
            ],
        )
