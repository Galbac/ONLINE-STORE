from html import escape

from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError, OrderNotFoundError, OrderPrintFormatError
from source.schemas.pydantic.order import AdminOrderPrintItemResponse, AdminOrderPrintResponse
from source.services.admin_auth import STAFF_ROLES


class AdminOrderPrintService:
    def _check_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        permissions = permission_service.get_user_permissions(role=user.role)
        if "admin:orders:read" not in permissions and "admin:orders:print" not in permissions:
            raise AdminAuthAccessDeniedError

    async def get_print_data(
        self,
        *,
        session,
        user,
        order_id: int,
        permission_service,
        order_repository,
        order_item_repository,
        address_repository,
        pickup_point_repository,
    ) -> AdminOrderPrintResponse:
        self._check_permission(user=user, permission_service=permission_service)

        order = await order_repository.admin_get_by_id(session=session, order_id=order_id)
        if order is None:
            raise OrderNotFoundError

        order_items = await order_item_repository.get_by_order_id(session=session, order_id=order.id)
        address = None
        if order.delivery_type == "delivery" and order.address_id is not None:
            address = await address_repository.get_by_id(session=session, address_id=order.address_id)
        pickup_point = None
        if order.delivery_type == "pickup" and order.pickup_point_id is not None:
            pickup_point = await pickup_point_repository.get_by_id(session=session, pickup_point_id=order.pickup_point_id)

        return AdminOrderPrintResponse(
            order_number=order.order_number,
            created_at=order.created_date,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            customer_email=order.customer_email,
            delivery_type=order.delivery_type,
            address=self._format_address(address=address, pickup_point=pickup_point, delivery_type=order.delivery_type),
            items=[
                AdminOrderPrintItemResponse(
                    name=item.product_name,
                    quantity=item.quantity,
                    unit=item.unit,
                    comment=None,
                )
                for item in order_items
            ],
            comment=order.comment,
            final_price=order.final_price,
        )

    def validate_format(self, *, format: str) -> str:
        normalized_format = format.strip().lower()
        if normalized_format not in {"html", "json"}:
            raise OrderPrintFormatError
        return normalized_format

    def render_html(self, *, data: AdminOrderPrintResponse) -> str:
        items_html = "\n".join(
            "<tr>"
            f"<td>{escape(item.name)}</td>"
            f"<td>{escape(str(item.quantity))}</td>"
            f"<td>{escape(item.unit)}</td>"
            f"<td>{escape(item.comment or '')}</td>"
            "</tr>"
            for item in data.items
        )
        return (
            "<!doctype html>"
            "<html><head><meta charset=\"utf-8\">"
            f"<title>Заказ {escape(data.order_number)}</title>"
            "<style>"
            "body{font-family:Arial,sans-serif;color:#111;margin:24px;}"
            "h1{font-size:22px;margin:0 0 16px;}"
            "table{width:100%;border-collapse:collapse;margin-top:16px;}"
            "th,td{border:1px solid #ccc;padding:8px;text-align:left;}"
            ".meta{margin:4px 0;}"
            "</style></head><body>"
            f"<h1>Заказ {escape(data.order_number)}</h1>"
            f"<div class=\"meta\">Дата: {escape(data.created_at.isoformat())}</div>"
            f"<div class=\"meta\">Клиент: {escape(data.customer_name)}</div>"
            f"<div class=\"meta\">Телефон: {escape(data.customer_phone)}</div>"
            f"<div class=\"meta\">Получение: {escape(data.delivery_type)}</div>"
            f"<div class=\"meta\">Адрес: {escape(data.address or '')}</div>"
            f"<div class=\"meta\">Комментарий: {escape(data.comment or '')}</div>"
            "<table><thead><tr><th>Товар</th><th>Количество</th><th>Ед.</th><th>Комментарий</th></tr></thead>"
            f"<tbody>{items_html}</tbody></table>"
            f"<div class=\"meta\">Итого: {escape(str(data.final_price))}</div>"
            "</body></html>"
        )

    def _format_address(self, *, address, pickup_point, delivery_type: str) -> str | None:
        if delivery_type == "delivery" and address is not None:
            parts = [address.city, address.street, address.house]
            if getattr(address, "building", None):
                parts.append(f"корп. {address.building}")
            result = ", ".join(part for part in parts if part)
            if getattr(address, "apartment", None):
                result = f"{result}, кв. {address.apartment}"
            return result
        if delivery_type == "pickup" and pickup_point is not None:
            return ", ".join(part for part in [pickup_point.city, pickup_point.address] if part)
        return None
