import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from source.config.settings import settings
from source.errors.auth import OneCSyncError
from source.schemas.pydantic.one_c import (
    OneCCategoryImportItem,
    OneCCategoryImportRequest,
    OneCImportItemErrorResponse,
    OneCImportResultResponse,
)
from source.utils.slug import generate_slug, normalize_slug


class OneCIntegrationService:
    async def mark_order_pending_sync(self, *, order) -> None:
        order.sync_status = "pending"

    async def mark_order_cancel_pending_sync(self, *, order) -> None:
        order.sync_status = "pending_cancel" if order.sync_status not in {"pending", "cancelled", "no_sync_needed"} else "cancelled"

    async def mark_cancel_pending(self, *, order) -> None:
        await self.mark_order_cancel_pending_sync(order=order)

    async def sync_order(self, *, payload: dict) -> dict:
        if not settings.one_c.api_url:
            raise OneCSyncError("1C API URL is not configured")

        url = settings.one_c.api_url.rstrip("/") + "/orders"
        headers = {"Content-Type": "application/json"}
        if settings.one_c.api_token:
            headers["Authorization"] = f"Bearer {settings.one_c.api_token}"

        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore")
            raise OneCSyncError(error_body or f"1C HTTP error {error.code}") from error
        except URLError as error:
            raise OneCSyncError(str(error.reason)) from error

        if not response_body:
            return {}
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            raise OneCSyncError("Invalid 1C response") from error


class CategorySyncService:
    async def upsert_categories_from_1c(
        self,
        *,
        session,
        data: OneCCategoryImportRequest,
        category_repository,
    ) -> OneCImportResultResponse:
        now = datetime.now(settings.tz)
        external_ids = {item.external_1c_id for item in data.items}
        parent_external_ids = {
            item.parent_external_1c_id
            for item in data.items
            if item.parent_external_1c_id is not None
        }
        existing_categories = await category_repository.get_by_external_1c_ids(
            session=session,
            external_1c_ids=external_ids | parent_external_ids,
        )
        categories_by_external_id = {
            category.external_1c_id: category
            for category in existing_categories
            if category.external_1c_id is not None
        }

        candidate_slugs = {self._target_slug(item=item) for item in data.items}
        slug_categories = await category_repository.get_by_slugs(session=session, slugs=candidate_slugs)
        taken_slugs = {
            category.slug: category.external_1c_id
            for category in slug_categories
        }

        errors: list[OneCImportItemErrorResponse] = []
        skipped = 0
        create_payloads: list[dict] = []
        update_categories = []
        process_items: list[OneCCategoryImportItem] = []

        payload_external_ids = {item.external_1c_id for item in data.items}
        seen_external_ids: set[str] = set()
        for item in data.items:
            if item.external_1c_id in seen_external_ids:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        external_1c_id=item.external_1c_id,
                        message="Дублирующийся external_1c_id в batch",
                        field="external_1c_id",
                    ),
                )
                continue
            seen_external_ids.add(item.external_1c_id)

            if item.parent_external_1c_id and (
                item.parent_external_1c_id not in categories_by_external_id
                and item.parent_external_1c_id not in payload_external_ids
            ):
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        external_1c_id=item.external_1c_id,
                        message="Родительская категория не найдена",
                        field="parent_external_1c_id",
                    ),
                )
                continue

            category = categories_by_external_id.get(item.external_1c_id)
            slug = self._resolve_slug(
                item=item,
                category=category,
                taken_slugs=taken_slugs,
            )
            taken_slugs[slug] = item.external_1c_id
            process_items.append(item)

            if category is None:
                create_payloads.append(
                    {
                        "external_1c_id": item.external_1c_id,
                        "name": item.name,
                        "slug": slug,
                        "parent_id": None,
                        "sort_order": item.sort_order,
                        "is_active": item.is_active,
                        "sync_status": "synced",
                        "last_sync_at": now,
                    },
                )
                continue

            category.name = item.name
            category.slug = slug
            category.is_active = item.is_active
            category.sort_order = item.sort_order
            category.sync_status = "synced"
            category.last_sync_at = now
            update_categories.append(category)

        created_categories = await category_repository.bulk_create(session=session, items=create_payloads)
        for category in created_categories:
            categories_by_external_id[category.external_1c_id] = category

        parent_updates = []
        for item in process_items:
            category = categories_by_external_id[item.external_1c_id]
            parent_id = None
            if item.parent_external_1c_id is not None:
                parent = categories_by_external_id.get(item.parent_external_1c_id)
                parent_id = parent.id if parent is not None else None
            if category.parent_id != parent_id:
                category.parent_id = parent_id
                parent_updates.append(category)

        categories_to_update = list({category.id: category for category in update_categories + parent_updates if category.id is not None}.values())
        if categories_to_update:
            await category_repository.bulk_update(session=session, categories=categories_to_update)

        return OneCImportResultResponse(
            created=len(created_categories),
            updated=len({category.id for category in update_categories if category.id is not None}),
            skipped=skipped,
            errors=errors,
        )

    def _target_slug(self, *, item: OneCCategoryImportItem) -> str:
        slug = normalize_slug(item.slug) if item.slug else generate_slug(item.name)
        return slug or f"category-{normalize_slug(item.external_1c_id)}"

    def _resolve_slug(self, *, item: OneCCategoryImportItem, category, taken_slugs: dict[str, str | None]) -> str:
        current_external_id = item.external_1c_id
        target_slug = self._target_slug(item=item)
        if category is not None and not self._can_update_slug(category=category, item=item):
            return category.slug
        slug = target_slug
        suffix = normalize_slug(current_external_id).replace(" ", "-") or "1c"
        counter = 2
        while slug in taken_slugs and taken_slugs[slug] != current_external_id:
            slug = f"{target_slug}-{suffix}"
            if slug in taken_slugs and taken_slugs[slug] != current_external_id:
                slug = f"{target_slug}-{suffix}-{counter}"
                counter += 1
        return slug

    def _can_update_slug(self, *, category, item: OneCCategoryImportItem) -> bool:
        if item.slug is not None:
            return True
        return category.slug == generate_slug(category.name)


class IntegrationLogService:
    async def create_log(
        self,
        *,
        session,
        integration_log_repository,
        status: str,
        request_payload: dict | None,
        response_payload: dict | None,
        error_message: str | None = None,
    ) -> None:
        await integration_log_repository.create(
            session=session,
            system="1c",
            entity_type="categories",
            entity_id=0,
            action="inbound_import",
            status=status,
            request_payload=request_payload,
            response_payload=response_payload,
            error_message=error_message,
        )


class OneCImportService:
    async def import_categories(
        self,
        *,
        session,
        redis_service,
        data: OneCCategoryImportRequest,
        commiter,
        category_repository,
        integration_log_repository,
        category_sync_service: CategorySyncService,
        integration_log_service: IntegrationLogService,
        category_cache_service,
        admin_category_cache_service,
        product_cache_service,
    ) -> OneCImportResultResponse:
        result = await category_sync_service.upsert_categories_from_1c(
            session=session,
            data=data,
            category_repository=category_repository,
        )
        status = "partial" if result.errors else "success"
        await integration_log_service.create_log(
            session=session,
            integration_log_repository=integration_log_repository,
            status=status,
            request_payload=data.model_dump(),
            response_payload=result.model_dump(),
        )
        await commiter.commit()

        await category_cache_service.invalidate_all(redis_service=redis_service)
        await admin_category_cache_service.invalidate_all(redis_service=redis_service)
        await product_cache_service.invalidate_lists(redis_service=redis_service)
        return result
