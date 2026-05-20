from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError, OrderNotFoundError
from source.schemas.pydantic.order import (
    AdminOrderAddressResponse,
    AdminOrderCustomerResponse,
    AdminOrderDetailResponse,
    AdminOrderItemResponse,
    AdminOrderListQueryParams,
    AdminOrderListResponse,
    AdminOrderPaymentResponse,
    AdminOrderPickupPointResponse,
    AdminOrderStatusResponse,
    AdminOrderStatusHistoryItemResponse,
    AdminOrderStatusUpdateRequest,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminOrderService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:orders:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_status_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:orders:update_status" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_orders(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminOrderListQueryParams,
        permission_service,
        order_repository,
        order_cache_service,
    ) -> AdminOrderListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_orders = await order_cache_service.get_admin_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_orders is not None:
            return cached_orders

        items = await order_repository.admin_get_list(session=session, query=normalized_query)
        total = await order_repository.admin_count(session=session, query=normalized_query)
        response = AdminOrderListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await order_cache_service.set_admin_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.orders.admin_list_cache_ttl_seconds,
        )
        return response

    async def get_order_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        order_id: int,
        permission_service,
        order_repository,
        order_item_repository,
        address_repository,
        pickup_point_repository,
        payment_repository,
        order_status_history_repository,
        order_cache_service,
    ) -> AdminOrderDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_order = await order_cache_service.get_admin_detail(
            redis_service=redis_service,
            order_id=order_id,
        )
        if cached_order is not None:
            return cached_order

        order = await order_repository.admin_get_by_id(session=session, order_id=order_id)
        if order is None:
            raise OrderNotFoundError

        order_items = await order_item_repository.get_by_order_id(session=session, order_id=order.id)
        payment = await payment_repository.get_by_order_id(session=session, order_id=order.id)
        status_history = await order_status_history_repository.get_by_order_id(session=session, order_id=order.id)
        address = None
        if order.address_id is not None:
            address = await address_repository.get_by_id(session=session, address_id=order.address_id)
        pickup_point = None
        if order.pickup_point_id is not None:
            pickup_point = await pickup_point_repository.get_by_id(session=session, pickup_point_id=order.pickup_point_id)

        response = AdminOrderDetailResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            customer=AdminOrderCustomerResponse(
                id=order.user_id,
                name=order.customer_name,
                phone=order.customer_phone,
                email=order.customer_email,
            ),
            address=self._build_address_response(address),
            pickup_point=self._build_pickup_point_response(pickup_point),
            items=[self._build_item_response(item) for item in order_items],
            payment=self._build_payment_response(payment),
            status_history=[self._build_status_history_response(item) for item in status_history],
            comment=order.comment,
            cancel_reason=order.cancel_reason,
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            promo_discount_amount=order.promo_discount_amount,
            delivery_price=order.delivery_price,
            final_price=order.final_price,
            sync_status=order.sync_status,
            external_1c_id=getattr(order, "external_1c_id", None),
            created_at=order.created_date,
        )
        await order_cache_service.set_admin_detail(
            redis_service=redis_service,
            order_id=order_id,
            response=response,
            ttl_seconds=settings.orders.admin_detail_cache_ttl_seconds,
        )
        return response

    async def update_status(
        self,
        *,
        session,
        commiter,
        redis_service: RedisService,
        user,
        order_id: int,
        data: AdminOrderStatusUpdateRequest,
        permission_service,
        order_repository,
        order_status_history_repository,
        order_status_service,
        notification_service,
        notification_repository,
        email_service,
        telegram_service,
        order_cache_service,
        profile_cache_service,
    ) -> AdminOrderStatusResponse:
        self._check_update_status_permission(user=user, permission_service=permission_service)

        order = await order_repository.admin_get_by_id(session=session, order_id=order_id)
        if order is None:
            raise OrderNotFoundError

        old_status = order.status
        order_status_service.validate_transition(current_status=old_status, new_status=data.status)
        sync_status = "pending_status_update" if order_status_service.affects_one_c(status=data.status) else None

        try:
            order = await order_repository.update_status(
                session=session,
                order=order,
                status=data.status,
                sync_status=sync_status,
            )
            await order_status_history_repository.create(
                session=session,
                order_id=order.id,
                old_status=old_status,
                status=data.status,
                comment=data.comment,
                changed_by=user.id,
            )
            if data.notify_customer:
                await notification_service.notify_order_status_changed(
                    session=session,
                    order=order,
                    notification_repository=notification_repository,
                    email_service=email_service,
                    telegram_service=telegram_service,
                )
            await commiter.commit()
        except Exception:
            await commiter.rollback()
            raise

        await order_cache_service.invalidate_admin_orders(redis_service=redis_service)
        await order_cache_service.invalidate_detail(redis_service=redis_service, user_id=order.user_id, order_id=order.id)
        await order_cache_service.invalidate_status(redis_service=redis_service, user_id=order.user_id, order_id=order.id)
        await order_cache_service.invalidate_my_orders(redis_service=redis_service, user_id=order.user_id)
        await profile_cache_service.delete_summary(redis_service=redis_service, user_id=order.user_id)

        return AdminOrderStatusResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            updated_at=order.updated_date,
        )

    def _build_address_response(self, address) -> AdminOrderAddressResponse | None:
        if address is None:
            return None
        return AdminOrderAddressResponse(
            city=address.city,
            street=address.street,
            house=address.house,
            apartment=address.apartment,
        )

    def _build_pickup_point_response(self, pickup_point) -> AdminOrderPickupPointResponse | None:
        if pickup_point is None:
            return None
        return AdminOrderPickupPointResponse(
            id=pickup_point.id,
            name=pickup_point.name,
            city=pickup_point.city,
            address=pickup_point.address,
        )

    def _build_item_response(self, item) -> AdminOrderItemResponse:
        return AdminOrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit=item.unit,
            price=item.price,
            final_price=item.final_price,
        )

    def _build_payment_response(self, payment) -> AdminOrderPaymentResponse | None:
        if payment is None:
            return None
        return AdminOrderPaymentResponse(
            id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            paid_at=payment.paid_at,
            cancelled_at=payment.cancelled_at,
            refund_status=payment.refund_status,
        )

    def _build_status_history_response(self, item) -> AdminOrderStatusHistoryItemResponse:
        return AdminOrderStatusHistoryItemResponse(
            status=item.status,
            created_at=item.created_date,
            comment=getattr(item, "comment", None),
        )
