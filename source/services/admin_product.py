from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.product import (
    ProductBarcodeAlreadyExistsError,
    ProductNotFoundError,
    ProductSkuAlreadyExistsError,
    ProductSlugAlreadyExistsError,
)
from source.schemas.pydantic.admin_product import (
    AdminProductCreateRequest,
    AdminProductDetailResponse,
    AdminProductImageResponse,
    AdminProductListQueryParams,
    AdminProductListResponse,
    AdminProductSeoResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminProductService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:products:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:products:create" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_products(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminProductListQueryParams,
        permission_service,
        product_repository,
        admin_product_cache_service,
    ) -> AdminProductListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_products = await admin_product_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_products is not None:
            return cached_products

        items = await product_repository.admin_get_list(session=session, query=normalized_query)
        total = await product_repository.admin_count(session=session, query=normalized_query)
        response = AdminProductListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_product_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.admin_list_cache_ttl_seconds,
        )
        return response

    async def create_product(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminProductCreateRequest,
        commiter,
        permission_service,
        product_repository,
        category_repository,
        admin_audit_log_repository,
        product_cache_service,
        admin_product_cache_service,
        category_cache_service,
    ) -> AdminProductDetailResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        if await product_repository.get_by_slug(session=session, slug=data.slug) is not None:
            raise ProductSlugAlreadyExistsError
        if data.sku is not None and await product_repository.get_by_sku(session=session, sku=data.sku) is not None:
            raise ProductSkuAlreadyExistsError
        if data.barcode is not None and await product_repository.get_by_barcode(session=session, barcode=data.barcode) is not None:
            raise ProductBarcodeAlreadyExistsError

        category = await category_repository.get_by_id(session=session, category_id=data.category_id)
        if category is None:
            raise CategoryNotFoundError

        product = await product_repository.create(
            session=session,
            name=data.name,
            slug=data.slug,
            description=data.description,
            category_id=data.category_id,
            price=data.price,
            old_price=data.old_price,
            unit=data.unit,
            product_type=data.product_type,
            quantity_step=data.quantity_step,
            min_quantity=data.min_quantity,
            stock_quantity=data.stock_quantity,
            low_stock_threshold=data.low_stock_threshold,
            is_active=data.is_active,
            is_available=data.is_available,
            article=data.sku,
            barcode=data.barcode,
            meta_title=data.meta_title,
            meta_description=data.meta_description,
            sync_status="manual",
        )
        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_product_create",
            status="success",
            details={
                "product_id": product.id,
                "name": product.name,
                "slug": product.slug,
                "category_id": product.category_id,
            },
        )
        await commiter.commit()

        await product_cache_service.invalidate_all(redis_service=redis_service)
        await admin_product_cache_service.invalidate_all(redis_service=redis_service)
        await category_cache_service.invalidate_all(redis_service=redis_service)

        return AdminProductDetailResponse(
            id=product.id,
            name=product.name,
            slug=product.slug,
            description=product.description,
            category_id=product.category_id,
            price=product.price,
            old_price=product.old_price,
            unit=product.unit,
            product_type=product.product_type,
            quantity_step=product.quantity_step,
            min_quantity=product.min_quantity,
            stock_quantity=product.stock_quantity,
            low_stock_threshold=product.low_stock_threshold,
            is_active=product.is_active,
            is_available=product.is_available,
            sku=product.article,
            barcode=product.barcode,
            external_1c_id=product.external_1c_id,
            sync_status=product.sync_status,
            images=[],
            seo=AdminProductSeoResponse(
                meta_title=product.meta_title,
                meta_description=product.meta_description,
            ),
        )

    async def get_product_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        product_id: int,
        permission_service,
        product_repository,
        product_image_repository,
        discount_repository,
        admin_product_cache_service,
    ) -> AdminProductDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_product = await admin_product_cache_service.get_detail(
            redis_service=redis_service,
            product_id=product_id,
        )
        if cached_product is not None:
            return cached_product

        row = await product_repository.admin_get_by_id(session=session, product_id=product_id)
        if row is None:
            raise ProductNotFoundError
        product, _category = row

        images = await product_image_repository.get_by_product_id(session=session, product_id=product.id)
        await discount_repository.get_by_product_id(session=session, product_id=product.id)
        response = AdminProductDetailResponse(
            id=product.id,
            name=product.name,
            slug=product.slug,
            description=product.description,
            category_id=product.category_id,
            price=product.price,
            old_price=product.old_price,
            unit=product.unit,
            product_type=product.product_type,
            quantity_step=product.quantity_step,
            min_quantity=product.min_quantity,
            stock_quantity=product.stock_quantity,
            low_stock_threshold=product.low_stock_threshold,
            is_active=product.is_active,
            is_available=product.is_available,
            sku=product.article,
            barcode=product.barcode,
            external_1c_id=product.external_1c_id,
            sync_status=product.sync_status,
            images=[
                AdminProductImageResponse(
                    id=image.id,
                    url=image.url,
                    sort_order=image.sort_order,
                )
                for image in images
            ],
            seo=AdminProductSeoResponse(
                meta_title=product.meta_title,
                meta_description=product.meta_description,
            ),
        )
        await admin_product_cache_service.set_detail(
            redis_service=redis_service,
            product_id=product.id,
            response=response,
            ttl_seconds=settings.products.admin_detail_cache_ttl_seconds,
        )
        return response
