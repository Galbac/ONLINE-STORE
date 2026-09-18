import csv
import io
from datetime import datetime, UTC
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, require_permission
from source.common.commiter import Commiter
from source.db.models.order import Order
from source.db.models.order_status_history import OrderStatusHistory
from source.db.models.product import Product
from source.db.models.user import User
from source.repositories.loyalty import LoyaltyRepository
from source.repositories.order import OrderRepository
from source.repositories.order_status_history import OrderStatusHistoryRepository
from source.schemas.pydantic.order import (
    AdminOrderListItemResponse,
    AdminOrderListResponse,
    AdminOrderStatusResponse,
)
from source.services.loyalty import LoyaltyService
from source.services.notifications import TelegramNotificationService

router = APIRouter(prefix="/admin", tags=["admin-operations"])


@router.get("/orders/assembly", response_model=AdminOrderListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_orders_for_assembly(
    current_user: User = Depends(require_permission("admin:orders:pick")),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminOrderListResponse:
    stmt = (
        select(Order)
        .where(Order.status.in_(["paid", "confirmed", "assembling"]))
        .order_by(Order.created_date.asc())
        .limit(100)
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())
    items = [order_repository._build_admin_order_response(o) for o in orders]
    return AdminOrderListResponse(items=items, total=len(items), page=1, limit=100, pages=1 if items else 0)


@router.post("/orders/{order_id}/start-assembly", response_model=AdminOrderStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def start_order_assembly(
    order_id: int,
    current_user: User = Depends(require_permission("admin:orders:pick")),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    commiter: FromDishka[Commiter] = None,
) -> AdminOrderStatusResponse:
    order = await order_repository.get_by_id(session=session, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    old_status = order.status
    order.status = "assembling"
    session.add(order)

    await order_status_history_repository.create(
        session=session,
        order_id=order.id,
        old_status=old_status,
        status="assembling",
        comment="Сборщик начал комплектовать заказ",
        changed_by=current_user.id,
    )
    await commiter.commit()
    return AdminOrderStatusResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        updated_at=order.updated_date,
    )


@router.post("/orders/{order_id}/complete-assembly", response_model=AdminOrderStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def complete_order_assembly(
    order_id: int,
    current_user: User = Depends(require_permission("admin:orders:pick")),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    commiter: FromDishka[Commiter] = None,
) -> AdminOrderStatusResponse:
    order = await order_repository.get_by_id(session=session, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    old_status = order.status
    order.status = "assembled"
    session.add(order)

    await order_status_history_repository.create(
        session=session,
        order_id=order.id,
        old_status=old_status,
        status="assembled",
        comment="Заказ полностью собран и упакован",
        changed_by=current_user.id,
    )
    await commiter.commit()
    return AdminOrderStatusResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        updated_at=order.updated_date,
    )


@router.get("/orders/courier/queue", response_model=AdminOrderListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_courier_orders_queue(
    current_user: User = Depends(require_permission("admin:orders:deliver")),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminOrderListResponse:
    stmt = (
        select(Order)
        .where(
            Order.delivery_type == "delivery",
            Order.status.in_(["assembled", "in_delivery"]),
        )
        .order_by(Order.created_date.asc())
        .limit(100)
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())
    items = [order_repository._build_admin_order_response(o) for o in orders]
    return AdminOrderListResponse(items=items, total=len(items), page=1, limit=100, pages=1 if items else 0)


@router.post("/orders/{order_id}/take-delivery", response_model=AdminOrderStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def take_order_delivery(
    order_id: int,
    current_user: User = Depends(require_permission("admin:orders:deliver")),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    commiter: FromDishka[Commiter] = None,
) -> AdminOrderStatusResponse:
    order = await order_repository.get_by_id(session=session, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    old_status = order.status
    order.status = "in_delivery"
    session.add(order)

    await order_status_history_repository.create(
        session=session,
        order_id=order.id,
        old_status=old_status,
        status="in_delivery",
        comment=f"Курьер {current_user.name} забрал заказ в доставку",
        changed_by=current_user.id,
    )
    await commiter.commit()

    if telegram_service is not None:
        user = await session.get(User, order.user_id)
        if user and user.telegram_chat_id:
            try:
                await telegram_service.send_message(
                    chat_id=user.telegram_chat_id,
                    message=f"🚗 Курьер {current_user.name} выехал к вам с заказом #{order.order_number}!",
                )
            except Exception:
                pass

    return AdminOrderStatusResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        updated_at=order.updated_date,
    )


@router.post("/orders/{order_id}/mark-delivered", response_model=AdminOrderStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def mark_order_delivered(
    order_id: int,
    current_user: User = Depends(require_permission("admin:orders:deliver")),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    loyalty_repository: FromDishka[LoyaltyRepository] = None,
    loyalty_service: FromDishka[LoyaltyService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    commiter: FromDishka[Commiter] = None,
) -> AdminOrderStatusResponse:
    order = await order_repository.get_by_id(session=session, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    old_status = order.status
    order.status = "delivered"
    order.payment_status = "paid"
    session.add(order)

    await order_status_history_repository.create(
        session=session,
        order_id=order.id,
        old_status=old_status,
        status="delivered",
        comment=f"Заказ успешно доставлен покупателю курьером {current_user.name}",
        changed_by=current_user.id,
    )

    cashback_amount = int(float(order.final_price) * 0.05)
    if cashback_amount > 0:
        await loyalty_service.accrue_points(
            session=session,
            loyalty_repository=loyalty_repository,
            commiter=commiter,
            user_id=order.user_id,
            amount=cashback_amount,
            description=f"Кэшбэк 5% за выполненный заказ #{order.order_number}",
            order_id=order.id,
        )

    await commiter.commit()

    if telegram_service is not None:
        user = await session.get(User, order.user_id)
        if user and user.telegram_chat_id:
            try:
                await telegram_service.send_message(
                    chat_id=user.telegram_chat_id,
                    message=f"✅ Заказ #{order.order_number} доставлен! Вам начислено {cashback_amount} бонусов.",
                )
            except Exception:
                pass

    return AdminOrderStatusResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        updated_at=order.updated_date,
    )


@router.get("/orders/export")
@inject
async def export_orders_csv(
    current_user: User = Depends(require_permission("admin:orders:read")),
    session: FromDishka[AsyncSession] = None,
) -> Response:
    stmt = select(Order).order_by(desc(Order.created_date)).limit(1000)
    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID", "Номер заказа", "Дата", "Статус", "Оплата", "Тип доставки",
        "Сумма", "Клиент", "Телефон", "Email"
    ])
    for o in orders:
        writer.writerow([
            o.id,
            o.order_number,
            o.created_date.strftime("%Y-%m-%d %H:%M:%S") if o.created_date else "",
            o.status,
            o.payment_status,
            o.delivery_type,
            str(o.final_price),
            o.customer_name,
            o.customer_phone,
            o.customer_email or "",
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_export.csv"},
    )


@router.get("/products/export")
@inject
async def export_products_csv(
    current_user: User = Depends(require_permission("admin:products:read")),
    session: FromDishka[AsyncSession] = None,
) -> Response:
    stmt = select(Product).where(Product.is_deleted.is_(False)).order_by(Product.name.asc()).limit(5000)
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID", "Название", "Slug", "Цена", "Старая цена", "Остаток", "Ед. изм.",
        "Активен", "1С Код"
    ])
    for p in products:
        writer.writerow([
            p.id,
            p.name,
            p.slug,
            str(p.price),
            str(p.old_price) if p.old_price else "",
            str(p.stock),
            p.unit,
            "Да" if p.is_active else "Нет",
            p.external_1c_id or "",
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_export.csv"},
    )
