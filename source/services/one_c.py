import base64
import binascii
import json
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from source.config.settings import settings
from source.errors.auth import OneCSyncError
from source.schemas.pydantic.one_c import (
    OneCCategoryImportItem,
    OneCCategoryImportRequest,
    OneCImageImportItem,
    OneCImageImportRequest,
    OneCImportItemErrorResponse,
    OneCOrderSyncErrorRequest,
    OneCOrderCustomerResponse,
    OneCOrderDeliveryResponse,
    OneCOrderItemResponse,
    OneCOrderSyncResponse,
    OneCMarkOrderSyncedRequest,
    OneCOrderPayloadResponse,
    OneCOrderPaymentResponse,
    OneCOrdersPendingQueryParams,
    OneCOrdersPendingResponse,
    OneCOrderTotalsResponse,
    OneCPriceImportItem,
    OneCPriceImportRequest,
    OneCProductImportItem,
    OneCProductImportRequest,
    OneCStockImportItem,
    OneCStockImportRequest,
    OneCImportResultResponse,
)
from source.utils.upload import detect_mime_type, generate_safe_filename, get_file_extension, validate_file_size
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

    async def health_check(self, *, timeout_seconds: int) -> None:
        if not settings.one_c.api_url:
            raise OneCSyncError("1C API URL is not configured")

        url = settings.one_c.api_url.rstrip("/") + "/health"
        headers = {}
        if settings.one_c.api_token:
            headers["Authorization"] = f"Bearer {settings.one_c.api_token}"
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                if response.status >= 400:
                    raise OneCSyncError("1C health check failed")
        except HTTPError as error:
            raise OneCSyncError(f"1C HTTP error {error.code}") from error
        except URLError as error:
            raise OneCSyncError("1C unavailable") from error


class OneCOrderPayloadBuilder:
    def build_order_payload(
        self,
        *,
        order,
        order_items: list,
        products_by_id: dict[int, object],
        address,
        pickup_point,
        payment,
        delivery_time_slot,
    ) -> OneCOrderPayloadResponse:
        return OneCOrderPayloadResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            sync_status=order.sync_status,
            customer=OneCOrderCustomerResponse(
                name=order.customer_name,
                phone=order.customer_phone,
                email=order.customer_email,
            ),
            delivery=OneCOrderDeliveryResponse(
                type=order.delivery_type,
                address=self._build_delivery_address(order=order, address=address, pickup_point=pickup_point),
                date=order.delivery_date,
                time_slot=self._build_time_slot(delivery_time_slot=delivery_time_slot),
                pickup_point=pickup_point.name if pickup_point is not None else None,
            ),
            payment=OneCOrderPaymentResponse(
                method=order.payment_method,
                status=payment.status if payment is not None else order.payment_status,
            ),
            items=[
                OneCOrderItemResponse(
                    product_id=item.product_id,
                    product_external_1c_id=getattr(products_by_id.get(item.product_id), "external_1c_id", None),
                    name=item.product_name,
                    quantity=item.quantity,
                    unit=item.unit,
                    price=item.price,
                    final_price=item.final_price,
                )
                for item in order_items
            ],
            totals=OneCOrderTotalsResponse(
                subtotal=order.subtotal,
                discount_amount=order.discount_amount,
                promo_discount_amount=order.promo_discount_amount,
                delivery_price=order.delivery_price,
                final_price=order.final_price,
            ),
            created_at=order.created_date,
        )

    def _build_delivery_address(self, *, order, address, pickup_point) -> str | None:
        if order.delivery_type == "pickup":
            return pickup_point.address if pickup_point is not None else None
        if address is None:
            return None
        parts = [
            address.city,
            f"{address.street} {address.house}".strip(),
        ]
        if address.building:
            parts.append(f"корп. {address.building}")
        if address.apartment:
            parts.append(f"кв. {address.apartment}")
        return ", ".join(part for part in parts if part)

    def _build_time_slot(self, *, delivery_time_slot) -> str | None:
        if delivery_time_slot is None:
            return None
        if delivery_time_slot.label:
            return delivery_time_slot.label
        return f"{delivery_time_slot.start_time.strftime('%H:%M')}-{delivery_time_slot.end_time.strftime('%H:%M')}"


class OneCOrderService:
    async def get_pending_orders(
        self,
        *,
        session,
        query: OneCOrdersPendingQueryParams,
        order_repository,
        order_item_repository,
        payment_repository,
        address_repository,
        pickup_point_repository,
        delivery_time_slot_repository,
        product_repository,
        order_payload_builder: OneCOrderPayloadBuilder,
    ) -> OneCOrdersPendingResponse:
        orders = await order_repository.get_pending_sync(
            session=session,
            limit=query.limit,
            sync_status=query.status,
        )
        order_ids = [order.id for order in orders]
        order_items = await order_item_repository.get_by_order_ids(session=session, order_ids=order_ids)
        payments = await payment_repository.get_by_order_ids(session=session, order_ids=order_ids)
        addresses = await address_repository.get_by_ids(
            session=session,
            address_ids=[order.address_id for order in orders if order.address_id is not None],
        )
        pickup_points = await pickup_point_repository.get_by_ids(
            session=session,
            pickup_point_ids=[order.pickup_point_id for order in orders if order.pickup_point_id is not None],
        )
        delivery_time_slots = await delivery_time_slot_repository.get_by_ids(
            session=session,
            slot_ids=[order.delivery_time_slot_id for order in orders if order.delivery_time_slot_id is not None],
        )
        products = await product_repository.get_by_ids(
            session=session,
            product_ids=list({item.product_id for item in order_items}),
        )

        items_by_order_id: dict[int, list] = {}
        for item in order_items:
            items_by_order_id.setdefault(item.order_id, []).append(item)
        payments_by_order_id = {payment.order_id: payment for payment in payments}
        addresses_by_id = {address.id: address for address in addresses}
        pickup_points_by_id = {pickup_point.id: pickup_point for pickup_point in pickup_points}
        slots_by_id = {slot.id: slot for slot in delivery_time_slots}
        products_by_id = {product.id: product for product in products}

        payloads = [
            order_payload_builder.build_order_payload(
                order=order,
                order_items=items_by_order_id.get(order.id, []),
                products_by_id=products_by_id,
                address=addresses_by_id.get(order.address_id),
                pickup_point=pickup_points_by_id.get(order.pickup_point_id),
                payment=payments_by_order_id.get(order.id),
                delivery_time_slot=slots_by_id.get(order.delivery_time_slot_id),
            )
            for order in orders
        ]
        return OneCOrdersPendingResponse(items=payloads, total=len(payloads))

    async def mark_order_synced(
        self,
        *,
        session,
        redis_service,
        order_id: int,
        data: OneCMarkOrderSyncedRequest,
        commiter,
        order_repository,
        integration_log_repository,
        order_cache_service,
    ) -> OneCOrderSyncResponse | None:
        order = await order_repository.get_by_id(session=session, order_id=order_id)
        if order is None:
            return None

        now = datetime.now(settings.tz)
        external_1c_id = data.external_1c_id or order.external_1c_id
        order = await order_repository.update_sync_success(
            session=session,
            order=order,
            external_1c_id=external_1c_id,
            last_sync_at=now,
        )
        response = OneCOrderSyncResponse(
            order_id=order.id,
            order_number=order.order_number,
            sync_status=order.sync_status,
            external_1c_id=order.external_1c_id,
            last_sync_at=order.last_sync_at,
        )
        await integration_log_repository.create(
            session=session,
            system="1c",
            entity_type="orders",
            entity_id=order.id,
            action="inbound_mark_synced",
            status="success",
            request_payload={
                "direction": "inbound",
                "order_id": order.id,
                "external_1c_id": data.external_1c_id,
                "message": data.message,
            },
            response_payload=response.model_dump(),
            error_message=None,
        )
        await commiter.commit()

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=order.user_id,
            order_id=order.id,
        )
        return response

    async def mark_order_sync_error(
        self,
        *,
        session,
        redis_service,
        order_id: int,
        data: OneCOrderSyncErrorRequest,
        commiter,
        order_repository,
        integration_log_repository,
        order_cache_service,
        admin_order_cache_service,
    ) -> OneCOrderSyncResponse | None:
        order = await order_repository.get_by_id(session=session, order_id=order_id)
        if order is None:
            return None

        now = datetime.now(settings.tz)
        order = await order_repository.update_sync_error(
            session=session,
            order=order,
            sync_error=data.error,
            sync_error_code=data.error_code,
            last_sync_at=now,
        )
        response = OneCOrderSyncResponse(
            order_id=order.id,
            order_number=order.order_number,
            sync_status=order.sync_status,
            external_1c_id=order.external_1c_id,
            sync_error=order.sync_error,
            sync_error_code=getattr(order, "sync_error_code", None),
            last_sync_at=order.last_sync_at,
        )
        await integration_log_repository.create(
            session=session,
            system="1c",
            entity_type="orders",
            entity_id=order.id,
            action="inbound_sync_error",
            status="error",
            request_payload={
                "direction": "inbound",
                "order_id": order.id,
                "error": data.error,
                "error_code": data.error_code,
            },
            response_payload=response.model_dump(),
            error_message=data.error,
        )
        await commiter.commit()

        await admin_order_cache_service.invalidate_order(
            redis_service=redis_service,
            order_id=order.id,
        )
        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=order.user_id,
            order_id=order.id,
        )
        return response


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


class SlugService:
    async def generate_unique_slug(
        self,
        *,
        session,
        product_repository,
        name: str,
        external_1c_id: str,
        taken_slugs: dict[str, str | None] | None = None,
    ) -> str:
        base_slug = generate_slug(name) or f"product-{normalize_slug(external_1c_id)}"
        taken_slugs = taken_slugs if taken_slugs is not None else {}
        slug = base_slug
        suffix = normalize_slug(external_1c_id).replace(" ", "-") or "1c"
        counter = 2
        while not await self._is_slug_available(
            session=session,
            product_repository=product_repository,
            slug=slug,
            external_1c_id=external_1c_id,
            taken_slugs=taken_slugs,
        ):
            slug = f"{base_slug}-{suffix}"
            if not await self._is_slug_available(
                session=session,
                product_repository=product_repository,
                slug=slug,
                external_1c_id=external_1c_id,
                taken_slugs=taken_slugs,
            ):
                slug = f"{base_slug}-{suffix}-{counter}"
                counter += 1
        taken_slugs[slug] = external_1c_id
        return slug

    async def _is_slug_available(
        self,
        *,
        session,
        product_repository,
        slug: str,
        external_1c_id: str,
        taken_slugs: dict[str, str | None],
    ) -> bool:
        if slug not in taken_slugs:
            existing_products = await product_repository.get_by_slugs(session=session, slugs={slug})
            for product in existing_products:
                taken_slugs[product.slug] = product.external_1c_id
        return slug not in taken_slugs or taken_slugs[slug] == external_1c_id


class ProductSyncService:
    async def upsert_products_from_1c(
        self,
        *,
        session,
        data: OneCProductImportRequest,
        product_repository,
        category_repository,
        slug_service: SlugService,
    ) -> OneCImportResultResponse:
        now = datetime.now(settings.tz)
        product_external_ids = {item.external_1c_id for item in data.items}
        category_external_ids = {
            item.category_external_1c_id
            for item in data.items
            if item.category_external_1c_id is not None
        }
        existing_products = await product_repository.get_by_external_1c_ids(
            session=session,
            external_1c_ids=product_external_ids,
        )
        products_by_external_id = {
            product.external_1c_id: product
            for product in existing_products
            if product.external_1c_id is not None
        }
        categories = await category_repository.get_by_external_1c_ids(
            session=session,
            external_1c_ids=category_external_ids,
        )
        categories_by_external_id = {
            category.external_1c_id: category
            for category in categories
            if category.external_1c_id is not None
        }

        candidate_slugs = {generate_slug(item.name) for item in data.items}
        slug_products = await product_repository.get_by_slugs(session=session, slugs=candidate_slugs)
        taken_slugs = {
            product.slug: product.external_1c_id
            for product in slug_products
        }

        errors: list[OneCImportItemErrorResponse] = []
        skipped = 0
        create_payloads: list[dict] = []
        update_products = []
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

            category_id = None
            if item.category_external_1c_id is not None:
                category = categories_by_external_id.get(item.category_external_1c_id)
                if category is None:
                    skipped += 1
                    errors.append(
                        OneCImportItemErrorResponse(
                            external_1c_id=item.external_1c_id,
                            message="Категория из 1С не найдена",
                            field="category_external_1c_id",
                        ),
                    )
                    continue
                category_id = category.id

            product = products_by_external_id.get(item.external_1c_id)
            if product is None:
                slug = await slug_service.generate_unique_slug(
                    session=session,
                    product_repository=product_repository,
                    name=item.name,
                    external_1c_id=item.external_1c_id,
                    taken_slugs=taken_slugs,
                )
                create_payloads.append(
                    {
                        "external_1c_id": item.external_1c_id,
                        "name": item.name,
                        "slug": slug,
                        "article": item.sku,
                        "barcode": item.barcode,
                        "category_id": category_id,
                        "unit": item.unit,
                        "product_type": item.product_type,
                        "quantity_step": item.quantity_step,
                        "min_quantity": item.min_quantity,
                        "price": Decimal("0"),
                        "is_active": item.is_active,
                        "is_available": item.is_available,
                        "sync_status": "synced",
                        "last_sync_at": now,
                        "source": "1c",
                    },
                )
                continue

            if self._can_update_slug(product=product):
                product.slug = await slug_service.generate_unique_slug(
                    session=session,
                    product_repository=product_repository,
                    name=item.name,
                    external_1c_id=item.external_1c_id,
                    taken_slugs=taken_slugs,
                )
            product.name = item.name
            product.article = item.sku
            product.barcode = item.barcode
            product.category_id = category_id
            product.unit = item.unit
            product.product_type = item.product_type
            product.quantity_step = item.quantity_step
            product.min_quantity = item.min_quantity
            product.is_active = item.is_active
            product.is_available = item.is_available
            product.sync_status = "synced"
            product.last_sync_at = now
            product.source = "1c"
            update_products.append(product)

        created_products = await product_repository.bulk_create(session=session, items=create_payloads)
        if update_products:
            await product_repository.bulk_update(session=session, products=update_products)

        return OneCImportResultResponse(
            created=len(created_products),
            updated=len({product.id for product in update_products if product.id is not None}),
            skipped=skipped,
            errors=errors,
        )

    def _can_update_slug(self, *, product) -> bool:
        return product.slug == generate_slug(product.name)


class ProductPriceSyncService:
    async def update_prices_from_1c(
        self,
        *,
        session,
        data: OneCPriceImportRequest,
        product_repository,
        product_price_history_repository,
    ) -> OneCImportResultResponse:
        now = datetime.now(settings.tz)
        product_external_ids = {item.product_external_1c_id for item in data.items}
        products = await product_repository.get_by_external_1c_ids(
            session=session,
            external_1c_ids=product_external_ids,
        )
        products_by_external_id = {
            product.external_1c_id: product
            for product in products
            if product.external_1c_id is not None
        }

        errors: list[OneCImportItemErrorResponse] = []
        skipped = 0
        updated_products = []
        history_payloads: list[dict] = []
        seen_external_ids: set[str] = set()

        for item in data.items:
            item_errors = self._validate_item(item=item)
            if item_errors:
                skipped += 1
                errors.extend(item_errors)
                continue
            if item.product_external_1c_id in seen_external_ids:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        product_external_1c_id=item.product_external_1c_id,
                        message="Дублирующийся product_external_1c_id в batch",
                        field="product_external_1c_id",
                    ),
                )
                continue
            seen_external_ids.add(item.product_external_1c_id)

            product = products_by_external_id.get(item.product_external_1c_id)
            if product is None:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        product_external_1c_id=item.product_external_1c_id,
                        message="Товар не найден",
                        field="product_external_1c_id",
                    ),
                )
                continue

            previous_price = product.price
            if previous_price != item.price:
                history_payloads.append(
                    {
                        "product_id": product.id,
                        "old_price": previous_price,
                        "new_price": item.price,
                        "source": "1c",
                        "changed_at": now,
                    },
                )
            product.price = item.price
            product.old_price = item.old_price
            product.currency = item.currency
            product.price_updated_at = now
            product.sync_status = "synced"
            product.last_sync_at = now
            updated_products.append(product)

        if updated_products:
            await product_repository.bulk_update_prices(session=session, products=updated_products)
        if history_payloads:
            await product_price_history_repository.bulk_create(session=session, items=history_payloads)

        return OneCImportResultResponse(
            updated=len({product.id for product in updated_products if product.id is not None}),
            skipped=skipped,
            errors=errors,
        )

    def _validate_item(self, *, item: OneCPriceImportItem) -> list[OneCImportItemErrorResponse]:
        errors: list[OneCImportItemErrorResponse] = []
        if item.price < 0:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="Цена не может быть отрицательной",
                    field="price",
                ),
            )
        if item.old_price is not None and item.old_price < 0:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="Старая цена не может быть отрицательной",
                    field="old_price",
                ),
            )
        if item.currency not in settings.admin_delivery.supported_currencies:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="Валюта не поддерживается",
                    field="currency",
                ),
            )
        return errors


class ProductStockSyncService:
    async def update_stocks_from_1c(
        self,
        *,
        session,
        data: OneCStockImportRequest,
        product_repository,
        stock_movement_service,
        stock_movement_repository,
    ) -> OneCImportResultResponse:
        now = datetime.now(settings.tz)
        product_external_ids = {item.product_external_1c_id for item in data.items}
        products = await product_repository.get_by_external_1c_ids(
            session=session,
            external_1c_ids=product_external_ids,
        )
        products_by_external_id = {
            product.external_1c_id: product
            for product in products
            if product.external_1c_id is not None
        }

        errors: list[OneCImportItemErrorResponse] = []
        skipped = 0
        updated_products = []
        movement_payloads: list[dict] = []
        seen_external_ids: set[str] = set()

        for item in data.items:
            item_errors = self._validate_item(item=item)
            if item_errors:
                skipped += 1
                errors.extend(item_errors)
                continue
            if item.product_external_1c_id in seen_external_ids:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        product_external_1c_id=item.product_external_1c_id,
                        message="Дублирующийся product_external_1c_id в batch",
                        field="product_external_1c_id",
                    ),
                )
                continue
            seen_external_ids.add(item.product_external_1c_id)

            product = products_by_external_id.get(item.product_external_1c_id)
            if product is None:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        product_external_1c_id=item.product_external_1c_id,
                        message="Товар не найден",
                        field="product_external_1c_id",
                    ),
                )
                continue

            previous_stock_quantity = product.stock_quantity
            if previous_stock_quantity != item.stock_quantity:
                movement_payloads.append(
                    {
                        "product_id": product.id,
                        "user_id": None,
                        "operation": "set",
                        "quantity": item.stock_quantity,
                        "previous_stock_quantity": previous_stock_quantity,
                        "new_stock_quantity": item.stock_quantity,
                        "old_quantity": previous_stock_quantity,
                        "new_quantity": item.stock_quantity,
                        "low_stock_threshold": product.low_stock_threshold,
                        "source": "1c",
                        "warehouse_external_1c_id": item.warehouse_external_1c_id,
                        "created_at": now,
                        "reason": "1C stock import",
                    },
                )

            product.stock_quantity = item.stock_quantity
            product.reserved_quantity = item.reserved_quantity if item.reserved_quantity is not None else 0
            product.stock_updated_at = now
            product.last_sync_at = now
            if settings.one_c.auto_availability_from_stock:
                if item.stock_quantity <= 0:
                    product.is_available = False
                elif product.is_active:
                    product.is_available = True
            updated_products.append(product)

        if updated_products:
            await product_repository.bulk_update_stocks(session=session, products=updated_products)
        if movement_payloads:
            await stock_movement_service.create_bulk(
                session=session,
                stock_movement_repository=stock_movement_repository,
                items=movement_payloads,
            )

        return OneCImportResultResponse(
            updated=len({product.id for product in updated_products if product.id is not None}),
            skipped=skipped,
            errors=errors,
        )

    def _validate_item(self, *, item: OneCStockImportItem) -> list[OneCImportItemErrorResponse]:
        errors: list[OneCImportItemErrorResponse] = []
        if item.stock_quantity < 0:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="Остаток не может быть отрицательным",
                    field="stock_quantity",
                ),
            )
        if item.reserved_quantity is not None and item.reserved_quantity < 0:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="Резерв не может быть отрицательным",
                    field="reserved_quantity",
                ),
            )
        return errors


class ImageDownloadService:
    async def download(self, *, image_url: str, max_size_bytes: int) -> tuple[bytes, str | None, str | None]:
        request = Request(image_url, method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                content = response.read(max_size_bytes + 1)
                content_type = response.headers.get_content_type()
        except (HTTPError, URLError, OSError) as error:
            raise ValueError("Не удалось скачать изображение") from error
        filename = Path(unquote(urlparse(image_url).path)).name or None
        return content, content_type, filename


class ProductImageSyncService:
    def __init__(self) -> None:
        self.changed_products: list = []

    async def import_images_from_1c(
        self,
        *,
        session,
        data: OneCImageImportRequest,
        product_repository,
        product_image_repository,
        upload_repository,
        storage_service,
        image_download_service: ImageDownloadService,
    ) -> OneCImportResultResponse:
        self.changed_products = []
        product_external_ids = {item.product_external_1c_id for item in data.items}
        products = await product_repository.get_by_external_1c_ids(
            session=session,
            external_1c_ids=product_external_ids,
        )
        products_by_external_id = {
            product.external_1c_id: product
            for product in products
            if product.external_1c_id is not None
        }

        errors: list[OneCImportItemErrorResponse] = []
        created = 0
        updated = 0
        skipped = 0

        for item in data.items:
            item_errors = self._validate_item(item=item)
            if item_errors:
                skipped += 1
                errors.extend(item_errors)
                continue

            product = products_by_external_id.get(item.product_external_1c_id)
            if product is None:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        product_external_1c_id=item.product_external_1c_id,
                        message="Товар не найден",
                        field="product_external_1c_id",
                    ),
                )
                continue

            existing_image = None
            if item.image_external_1c_id is not None:
                existing_image = await product_image_repository.get_by_external_1c_id(
                    session=session,
                    image_external_1c_id=item.image_external_1c_id,
                )
            product_images = await product_image_repository.get_active_models_by_product_id(
                session=session,
                product_id=product.id,
            )
            has_main_image = any(image.is_main for image in product_images)
            should_be_main = item.is_main or not has_main_image
            if should_be_main:
                await product_image_repository.unset_main_by_product_id(session=session, product_id=product.id)

            if existing_image is not None:
                await product_image_repository.update(
                    session=session,
                    image=existing_image,
                    sort_order=item.sort_order,
                    is_main=should_be_main,
                )
                updated += 1
                self.changed_products.append(product)
                continue

            try:
                file_id, image_url, external_url = await self._resolve_image_storage(
                    session=session,
                    item=item,
                    upload_repository=upload_repository,
                    storage_service=storage_service,
                    image_download_service=image_download_service,
                )
            except ValueError as error:
                skipped += 1
                errors.append(
                    OneCImportItemErrorResponse(
                        product_external_1c_id=item.product_external_1c_id,
                        message=str(error),
                    ),
                )
                continue

            await product_image_repository.create(
                session=session,
                product_id=product.id,
                file_id=file_id,
                url=image_url,
                sort_order=item.sort_order,
                is_main=should_be_main,
                image_external_1c_id=item.image_external_1c_id,
                external_url=external_url,
            )
            created += 1
            self.changed_products.append(product)

        return OneCImportResultResponse(
            created=created,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    def _validate_item(self, *, item: OneCImageImportItem) -> list[OneCImportItemErrorResponse]:
        errors: list[OneCImportItemErrorResponse] = []
        if item.sort_order < 0:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="sort_order не может быть отрицательным",
                    field="sort_order",
                ),
            )
        if item.image_url is None and item.content_base64 is None:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="Нужно передать image_url или content_base64",
                ),
            )
        if item.content_base64 is not None and item.filename is None:
            errors.append(
                OneCImportItemErrorResponse(
                    product_external_1c_id=item.product_external_1c_id,
                    message="filename обязателен для content_base64",
                    field="filename",
                ),
            )
        return errors

    async def _resolve_image_storage(
        self,
        *,
        session,
        item: OneCImageImportItem,
        upload_repository,
        storage_service,
        image_download_service: ImageDownloadService,
    ) -> tuple[int | None, str, str | None]:
        if item.image_url is not None and not settings.one_c.download_images:
            return None, item.image_url, item.image_url

        if item.content_base64 is not None:
            try:
                content = base64.b64decode(item.content_base64, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("Некорректный base64") from error
            filename = item.filename
            mime_type = detect_mime_type(content)
        else:
            content, header_mime_type, downloaded_filename = await image_download_service.download(
                image_url=item.image_url,
                max_size_bytes=settings.media.max_image_size_mb * 1024 * 1024,
            )
            filename = item.filename or downloaded_filename
            detected_mime_type = detect_mime_type(content)
            mime_type = detected_mime_type or header_mime_type

        if filename is None:
            raise ValueError("filename обязателен")
        max_size_bytes = settings.media.max_image_size_mb * 1024 * 1024
        try:
            validate_file_size(content=content, max_size_bytes=max_size_bytes)
        except Exception as error:
            raise ValueError("Файл слишком большой") from error
        if mime_type not in settings.media.allowed_image_type_set:
            raise ValueError("Тип изображения не поддерживается")
        detected_mime_type = detect_mime_type(content)
        if detected_mime_type is None or detected_mime_type != mime_type:
            raise ValueError("Некорректное изображение")
        extension = get_file_extension(filename)
        if extension not in settings.media.allowed_image_extension_set:
            raise ValueError("Расширение изображения не поддерживается")

        stored_filename = generate_safe_filename(extension=extension, entity_type="product")
        saved_url, storage_type = await storage_service.save_file(stored_filename=stored_filename, content=content)
        upload = await upload_repository.create(
            session=session,
            original_filename=filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            size=len(content),
            storage_type=storage_type,
            url=saved_url,
            entity_type="product",
            uploaded_by=None,
        )
        return upload.id, saved_url, None


class IntegrationLogService:
    async def create_log(
        self,
        *,
        session,
        integration_log_repository,
        status: str,
        request_payload: dict | None,
        response_payload: dict | None,
        entity_type: str = "categories",
        error_message: str | None = None,
    ) -> None:
        await integration_log_repository.create(
            session=session,
            system="1c",
            entity_type=entity_type,
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

    async def import_products(
        self,
        *,
        session,
        redis_service,
        data: OneCProductImportRequest,
        commiter,
        product_repository,
        category_repository,
        integration_log_repository,
        product_sync_service: ProductSyncService,
        slug_service: SlugService,
        integration_log_service: IntegrationLogService,
        product_cache_service,
        admin_product_cache_service,
        category_cache_service,
    ) -> OneCImportResultResponse:
        result = await product_sync_service.upsert_products_from_1c(
            session=session,
            data=data,
            product_repository=product_repository,
            category_repository=category_repository,
            slug_service=slug_service,
        )
        status = "partial" if result.errors else "success"
        await integration_log_service.create_log(
            session=session,
            integration_log_repository=integration_log_repository,
            status=status,
            request_payload=data.model_dump(),
            response_payload=result.model_dump(),
            entity_type="products",
        )
        await commiter.commit()

        await product_cache_service.invalidate_all(redis_service=redis_service)
        await admin_product_cache_service.invalidate_all(redis_service=redis_service)
        await category_cache_service.invalidate_tree(redis_service=redis_service)
        return result

    async def import_prices(
        self,
        *,
        session,
        redis_service,
        data: OneCPriceImportRequest,
        commiter,
        product_repository,
        product_price_history_repository,
        integration_log_repository,
        product_price_sync_service: ProductPriceSyncService,
        integration_log_service: IntegrationLogService,
        product_cache_service,
        cart_cache_service,
        admin_product_cache_service,
    ) -> OneCImportResultResponse:
        result = await product_price_sync_service.update_prices_from_1c(
            session=session,
            data=data,
            product_repository=product_repository,
            product_price_history_repository=product_price_history_repository,
        )
        status = "partial" if result.errors else "success"
        await integration_log_service.create_log(
            session=session,
            integration_log_repository=integration_log_repository,
            status=status,
            request_payload=data.model_dump(),
            response_payload=result.model_dump(),
            entity_type="product_prices",
        )
        await commiter.commit()

        await product_cache_service.invalidate_all(redis_service=redis_service)
        await cart_cache_service.invalidate_all(redis_service=redis_service)
        await admin_product_cache_service.invalidate_all(redis_service=redis_service)
        return result

    async def import_stocks(
        self,
        *,
        session,
        redis_service,
        data: OneCStockImportRequest,
        commiter,
        product_repository,
        stock_movement_repository,
        integration_log_repository,
        product_stock_sync_service: ProductStockSyncService,
        stock_movement_service,
        integration_log_service: IntegrationLogService,
        product_cache_service,
        cart_cache_service,
        admin_dashboard_cache_service,
        admin_product_cache_service,
    ) -> OneCImportResultResponse:
        result = await product_stock_sync_service.update_stocks_from_1c(
            session=session,
            data=data,
            product_repository=product_repository,
            stock_movement_service=stock_movement_service,
            stock_movement_repository=stock_movement_repository,
        )
        status = "partial" if result.errors else "success"
        await integration_log_service.create_log(
            session=session,
            integration_log_repository=integration_log_repository,
            status=status,
            request_payload=data.model_dump(),
            response_payload=result.model_dump(),
            entity_type="product_stocks",
        )
        await commiter.commit()

        await product_cache_service.invalidate_by_stock_changes(redis_service=redis_service, products=[])
        await cart_cache_service.invalidate_all(redis_service=redis_service)
        await admin_dashboard_cache_service.invalidate_low_stock(redis_service=redis_service)
        await admin_product_cache_service.invalidate_all(redis_service=redis_service)
        return result

    async def import_images(
        self,
        *,
        session,
        redis_service,
        data: OneCImageImportRequest,
        commiter,
        product_repository,
        product_image_repository,
        upload_repository,
        integration_log_repository,
        product_image_sync_service: ProductImageSyncService,
        image_download_service: ImageDownloadService,
        storage_service,
        integration_log_service: IntegrationLogService,
        product_cache_service,
        admin_product_cache_service,
    ) -> OneCImportResultResponse:
        result = await product_image_sync_service.import_images_from_1c(
            session=session,
            data=data,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            upload_repository=upload_repository,
            storage_service=storage_service,
            image_download_service=image_download_service,
        )
        status = "partial" if result.errors else "success"
        await integration_log_service.create_log(
            session=session,
            integration_log_repository=integration_log_repository,
            status=status,
            request_payload=data.model_dump(exclude={"items": {"__all__": {"content_base64"}}}),
            response_payload=result.model_dump(),
            entity_type="product_images",
        )
        await commiter.commit()

        changed_by_product_id = {
            product.id: product
            for product in product_image_sync_service.changed_products
            if product.id is not None
        }
        for product in changed_by_product_id.values():
            await product_cache_service.invalidate_product(
                redis_service=redis_service,
                product_id=product.id,
                slug=product.slug,
            )
            await admin_product_cache_service.invalidate_product(
                redis_service=redis_service,
                product_id=product.id,
            )
        return result
