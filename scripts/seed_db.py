import asyncio
import hashlib
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.config.settings import settings
from source.db.db_helper import db_helper
from source.db.models import (
    Address,
    AdminAuditLog,
    Cart,
    CartItem,
    Category,
    DeliverySettings,
    DeliveryTimeSlot,
    DeliveryZone,
    Favorite,
    IntegrationJob,
    IntegrationLog,
    Notification,
    NotificationLog,
    NotificationSettings,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentWebhookLog,
    PickupPoint,
    Product,
    ProductAvailabilityLog,
    ProductImage,
    ProductPriceHistory,
    PromoCode,
    PromoCodeUsage,
    RefreshToken,
    Refund,
    StockMovement,
    StoreSettings,
    Upload,
    User,
)
from source.db.models.choises.enum import UserRole
from source.db.models.discount import Discount, DiscountCategory, DiscountProduct
from source.db.models.promo_code import PromoCodeCategory, PromoCodeProduct
from source.services.password import PasswordService

ModelT = TypeVar("ModelT")


NOW = datetime.now(settings.tz)
PASSWORD = "StrongPassword123"


async def get_one(session: AsyncSession, model: type[ModelT], **filters: Any) -> ModelT | None:
    stmt = select(model)
    for field, value in filters.items():
        stmt = stmt.where(getattr(model, field) == value)
    return await session.scalar(stmt.limit(1))


async def get_or_create(session: AsyncSession, model: type[ModelT], defaults: dict[str, Any] | None = None, **filters: Any) -> ModelT:
    instance = await get_one(session, model, **filters)
    if instance is not None:
        return instance

    instance = model(**filters, **(defaults or {}))
    session.add(instance)
    await session.flush()
    return instance


async def seed_users(session: AsyncSession) -> dict[str, User]:
    password_hash = PasswordService().hash_password(PASSWORD)
    users = {
        "admin": await get_or_create(
            session,
            User,
            phone="+79990000001",
            defaults={
                "name": "Администратор",
                "email": "admin@example.com",
                "password_hash": password_hash,
                "role": UserRole.ADMIN,
                "is_active": True,
            },
        ),
        "manager": await get_or_create(
            session,
            User,
            phone="+79990000002",
            defaults={
                "name": "Менеджер",
                "email": "manager@example.com",
                "password_hash": password_hash,
                "role": UserRole.MANAGER,
                "is_active": True,
            },
        ),
        "customer": await get_or_create(
            session,
            User,
            phone="+79990000003",
            defaults={
                "name": "Иван Покупатель",
                "email": "customer@example.com",
                "password_hash": password_hash,
                "role": UserRole.CUSTOMER,
                "is_active": True,
            },
        ),
        "courier": await get_or_create(
            session,
            User,
            phone="+79990000004",
            defaults={
                "name": "Курьер",
                "email": "courier@example.com",
                "password_hash": password_hash,
                "role": UserRole.COURIER,
                "is_active": True,
            },
        ),
    }
    await session.flush()
    return users


async def seed_settings(session: AsyncSession) -> None:
    if await get_one(session, StoreSettings) is None:
        session.add(StoreSettings(shop_name="Grocery Store", phone="+79990000000", email="info@grocery.local"))
    if await get_one(session, DeliverySettings) is None:
        session.add(DeliverySettings(min_order_amount=Decimal("700.00"), base_price=Decimal("199.00")))
    if await get_one(session, NotificationSettings) is None:
        session.add(NotificationSettings(email_from="noreply@grocery.local", telegram_admin_chat_id="100000001"))
    await session.flush()


async def seed_catalog(session: AsyncSession, admin: User) -> tuple[dict[str, Category], dict[str, Product]]:
    uploads = [
        await get_or_create(
            session,
            Upload,
            stored_filename=f"seed/{slug}.jpg",
            defaults={
                "original_filename": f"{slug}.jpg",
                "mime_type": "image/jpeg",
                "size": 120000,
                "storage_type": "local",
                "url": f"/uploads/seed/{slug}.jpg",
                "entity_type": "catalog",
                "uploaded_by": admin.id,
            },
        )
        for slug in ("fruits", "vegetables", "milk", "bread")
    ]

    categories: dict[str, Category] = {}
    for index, (slug, name, description) in enumerate(
        (
            ("frukty-i-yagody", "Фрукты и ягоды", "Свежие фрукты и ягоды"),
            ("ovoshchi", "Овощи", "Овощи на каждый день"),
            ("molochnye-produkty", "Молочные продукты", "Молоко, сыр и йогурты"),
            ("khleb-i-vypechka", "Хлеб и выпечка", "Свежая выпечка"),
        )
    ):
        categories[slug] = await get_or_create(
            session,
            Category,
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "image_file_id": uploads[index].id,
                "image_url": uploads[index].url,
                "sort_order": index + 1,
                "is_active": True,
                "sync_status": "synced",
                "external_1c_id": f"cat-{index + 1:03}",
            },
        )

    products_data = (
        ("apple-gala", "Яблоки Гала", categories["frukty-i-yagody"], "кг", "weight", "149.90", "189.90", "48.000"),
        ("banana", "Бананы", categories["frukty-i-yagody"], "кг", "weight", "129.90", None, "36.000"),
        ("tomato", "Томаты", categories["ovoshchi"], "кг", "weight", "219.90", "249.90", "22.500"),
        ("cucumber", "Огурцы", categories["ovoshchi"], "кг", "weight", "179.90", None, "31.000"),
        ("milk-32", "Молоко 3.2%", categories["molochnye-produkty"], "шт", "piece", "89.90", None, "80.000"),
        ("cheese-gouda", "Сыр Гауда", categories["molochnye-produkty"], "шт", "piece", "329.90", "369.90", "18.000"),
        ("bread-rye", "Хлеб ржаной", categories["khleb-i-vypechka"], "шт", "piece", "59.90", None, "45.000"),
        ("croissant", "Круассан", categories["khleb-i-vypechka"], "шт", "piece", "79.90", None, "25.000"),
    )
    products: dict[str, Product] = {}
    for index, (slug, name, category, unit, product_type, price, old_price, stock) in enumerate(products_data, start=1):
        product = await get_or_create(
            session,
            Product,
            slug=slug,
            defaults={
                "category_id": category.id,
                "name": name,
                "article": f"ART-{index:04}",
                "barcode": f"46000000000{index:02}",
                "external_1c_id": f"product-{index:03}",
                "sync_status": "synced",
                "last_sync_at": NOW,
                "source": "seed",
                "description": f"{name}. Демо-товар для каталога.",
                "search_keywords": name.lower(),
                "preview_image_url": f"/uploads/seed/{slug}.jpg",
                "unit": unit,
                "product_type": product_type,
                "price": Decimal(price),
                "old_price": Decimal(old_price) if old_price else None,
                "price_updated_at": NOW,
                "stock_quantity": Decimal(stock),
                "stock_updated_at": NOW,
                "quantity_step": Decimal("0.100") if product_type == "weight" else Decimal("1.000"),
                "min_quantity": Decimal("0.500") if product_type == "weight" else Decimal("1.000"),
                "low_stock_threshold": Decimal("5.000"),
                "popularity": 100 - index,
                "is_active": True,
                "is_available": True,
            },
        )
        products[slug] = product
        await get_or_create(
            session,
            ProductImage,
            product_id=product.id,
            url=f"/uploads/seed/{slug}.jpg",
            defaults={
                "external_url": f"https://example.com/images/{slug}.jpg",
                "sort_order": 1,
                "is_main": True,
            },
        )
        await get_or_create(
            session,
            ProductPriceHistory,
            product_id=product.id,
            source="seed",
            defaults={
                "old_price": product.old_price or product.price,
                "new_price": product.price,
                "changed_at": NOW.replace(microsecond=0),
            },
        )
        await get_or_create(
            session,
            StockMovement,
            product_id=product.id,
            operation="income",
            reason="seed initial stock",
            defaults={
                "user_id": admin.id,
                "quantity": product.stock_quantity,
                "previous_stock_quantity": Decimal("0.000"),
                "new_stock_quantity": product.stock_quantity,
                "low_stock_threshold": product.low_stock_threshold,
                "source": "seed",
                "created_at": NOW,
            },
        )
        await get_or_create(
            session,
            ProductAvailabilityLog,
            product_id=product.id,
            reason="seed availability",
            defaults={"user_id": admin.id, "is_available": True, "status": "success"},
        )
    await session.flush()
    return categories, products


async def seed_delivery(session: AsyncSession, admin: User) -> tuple[DeliveryZone, PickupPoint, DeliveryTimeSlot]:
    zone = await get_or_create(
        session,
        DeliveryZone,
        name="Москва в пределах МКАД",
        city="Москва",
        defaults={
            "description": "Базовая зона доставки",
            "price": Decimal("199.00"),
            "free_delivery_from": Decimal("3000.00"),
            "min_order_amount": Decimal("700.00"),
            "sort_order": 1,
            "deleted_by": None,
        },
    )
    pickup = await get_or_create(
        session,
        PickupPoint,
        name="Магазин на Тверской",
        address="ул. Тверская, 10",
        defaults={
            "city": "Москва",
            "working_hours": "09:00-22:00",
            "phone": "+79990000000",
            "latitude": Decimal("55.760000"),
            "longitude": Decimal("37.610000"),
            "sort_order": 1,
        },
    )
    slot = await get_or_create(
        session,
        DeliveryTimeSlot,
        delivery_type="delivery",
        label="10:00-13:00",
        defaults={
            "pickup_point_id": None,
            "start_time": time(10, 0),
            "end_time": time(13, 0),
            "orders_limit": 10,
            "sort_order": 1,
        },
    )
    await get_or_create(
        session,
        DeliveryTimeSlot,
        delivery_type="pickup",
        pickup_point_id=pickup.id,
        label="13:00-16:00",
        defaults={"start_time": time(13, 0), "end_time": time(16, 0), "orders_limit": 20, "sort_order": 2},
    )
    await session.flush()
    return zone, pickup, slot


async def seed_marketing(
    session: AsyncSession,
    admin: User,
    categories: dict[str, Category],
    products: dict[str, Product],
) -> tuple[Discount, PromoCode]:
    discount = await get_or_create(
        session,
        Discount,
        name="Скидка на фрукты",
        defaults={
            "type": "catalog",
            "discount_type": "percent",
            "discount_value": Decimal("10.00"),
            "applicable_category_id": categories["frukty-i-yagody"].id,
            "starts_at": NOW - timedelta(days=1),
            "ends_at": NOW + timedelta(days=30),
        },
    )
    await get_or_create(session, DiscountCategory, discount_id=discount.id, category_id=categories["frukty-i-yagody"].id)
    await get_or_create(session, DiscountProduct, discount_id=discount.id, product_id=products["apple-gala"].id)

    promo_code = await get_or_create(
        session,
        PromoCode,
        code="WELCOME10",
        defaults={
            "name": "Скидка для первого заказа",
            "description": "10% на заказ от 1000 рублей",
            "discount_type": "percent",
            "discount_value": Decimal("10.00"),
            "min_order_amount": Decimal("1000.00"),
            "max_discount_amount": Decimal("500.00"),
            "usage_limit": 1000,
            "per_user_usage_limit": 1,
            "applicable_category_id": categories["frukty-i-yagody"].id,
            "allow_discounted_products": True,
            "starts_at": NOW - timedelta(days=1),
            "ends_at": NOW + timedelta(days=60),
        },
    )
    await get_or_create(session, PromoCodeCategory, promo_code_id=promo_code.id, category_id=categories["frukty-i-yagody"].id)
    await get_or_create(session, PromoCodeProduct, promo_code_id=promo_code.id, product_id=products["banana"].id)
    await session.flush()
    return discount, promo_code


async def seed_customer_flow(
    session: AsyncSession,
    users: dict[str, User],
    products: dict[str, Product],
    promo_code: PromoCode,
    zone: DeliveryZone,
    pickup: PickupPoint,
    slot: DeliveryTimeSlot,
) -> Order:
    customer = users["customer"]
    address = await get_or_create(
        session,
        Address,
        user_id=customer.id,
        title="Дом",
        defaults={
            "city": "Москва",
            "street": "Ленина",
            "house": "15",
            "apartment": "42",
            "floor": "8",
            "comment": "Позвонить за 10 минут",
            "is_default": True,
        },
    )
    cart = await get_or_create(session, Cart, user_id=customer.id, defaults={"promo_code_id": promo_code.id})
    for product in (products["apple-gala"], products["milk-32"]):
        quantity = Decimal("1.000")
        await get_or_create(
            session,
            CartItem,
            cart_id=cart.id,
            product_id=product.id,
            defaults={
                "name": product.name,
                "quantity": quantity,
                "unit": product.unit,
                "price": product.price,
                "total_price": product.price * quantity,
            },
        )
        await get_or_create(session, Favorite, user_id=customer.id, product_id=product.id)

    subtotal = Decimal("239.80")
    final_price = Decimal("414.82")
    order = await get_or_create(
        session,
        Order,
        order_number="SEED-0001",
        defaults={
            "user_id": customer.id,
            "address_id": address.id,
            "pickup_point_id": pickup.id,
            "delivery_zone_id": zone.id,
            "status": "created",
            "payment_method": "card",
            "payment_status": "paid",
            "delivery_type": "delivery",
            "delivery_date": date.today() + timedelta(days=1),
            "delivery_time_slot_id": slot.id,
            "delivery_price": Decimal("199.00"),
            "subtotal": subtotal,
            "discount_amount": Decimal("0.00"),
            "promo_discount_amount": Decimal("23.98"),
            "final_price": final_price,
            "customer_name": customer.name,
            "customer_phone": customer.phone,
            "customer_email": customer.email,
            "comment": "Демо-заказ",
            "sync_status": "pending",
            "items_count": 2,
        },
    )
    for product, quantity in ((products["apple-gala"], Decimal("1.000")), (products["milk-32"], Decimal("1.000"))):
        await get_or_create(
            session,
            OrderItem,
            order_id=order.id,
            product_id=product.id,
            defaults={
                "product_name": product.name,
                "product_slug": product.slug,
                "quantity": quantity,
                "unit": product.unit,
                "product_type": product.product_type,
                "price": product.price,
                "old_price": product.old_price,
                "discount_amount": Decimal("0.00"),
                "total_price": product.price * quantity,
                "final_price": product.price * quantity,
            },
        )
    await get_or_create(session, OrderStatusHistory, order_id=order.id, status="created", defaults={"comment": "Заказ создан", "changed_by": customer.id})
    await get_or_create(session, PromoCodeUsage, promo_code_id=promo_code.id, user_id=customer.id, order_id=order.id, defaults={"status": "applied"})
    await session.flush()
    return order


async def seed_payments_and_logs(session: AsyncSession, users: dict[str, User], order: Order) -> None:
    payment = await get_or_create(
        session,
        Payment,
        provider_payment_id="seed-payment-0001",
        defaults={
            "order_id": order.id,
            "amount": order.final_price,
            "currency": "RUB",
            "status": "paid",
            "provider": "yookassa",
            "payment_url": "https://payment.example.com/seed-payment-0001",
            "paid_at": NOW,
            "refund_status": "none",
        },
    )
    await get_or_create(
        session,
        PaymentWebhookLog,
        provider_event_id="seed-webhook-0001",
        defaults={
            "event_type": "payment.succeeded",
            "provider_payment_id": payment.provider_payment_id,
            "payment_id": payment.id,
            "payload": {"event": "payment.succeeded"},
            "processing_status": "processed",
        },
    )
    await get_or_create(
        session,
        Refund,
        provider_refund_id="seed-refund-0001",
        defaults={"payment_id": payment.id, "amount": Decimal("0.00"), "currency": "RUB", "status": "created", "reason": "demo"},
    )
    await get_or_create(
        session,
        Notification,
        user_id=users["customer"].id,
        title="Заказ создан",
        defaults={"type": "order", "message": f"Заказ {order.order_number} успешно создан", "is_read": False},
    )
    await get_or_create(
        session,
        NotificationLog,
        channel="email",
        recipient="customer@example.com",
        subject="Заказ создан",
        defaults={"message": f"Заказ {order.order_number} успешно создан", "status": "sent", "created_by": users["admin"].id},
    )
    await get_or_create(
        session,
        IntegrationJob,
        type="orders_export",
        started_by=users["admin"].id,
        defaults={
            "status": "finished",
            "full_sync": False,
            "started_at": NOW - timedelta(minutes=5),
            "finished_at": NOW,
            "result_payload": {"orders_exported": 1},
        },
    )
    await get_or_create(
        session,
        IntegrationLog,
        system="1c",
        entity_type="order",
        entity_id=order.id,
        action="export",
        defaults={
            "status": "success",
            "request_payload": {"order_number": order.order_number},
            "response_payload": {"external_id": "1c-order-seed-0001"},
        },
    )
    await get_or_create(
        session,
        AdminAuditLog,
        login=users["admin"].email,
        event="seed_database",
        defaults={
            "user_id": users["admin"].id,
            "status": "success",
            "ip_address": "127.0.0.1",
            "user_agent": "seed_db.py",
            "details": {"script": "scripts/seed_db.py"},
        },
    )
    await get_or_create(
        session,
        RefreshToken,
        token_hash=hashlib.sha256(b"seed-refresh-token").hexdigest(),
        defaults={"user_id": users["customer"].id, "expires_at": NOW + timedelta(days=30)},
    )
    await session.flush()


async def seed_bulk_catalog(session: AsyncSession, admin: User) -> dict[str, Product]:
    category_specs = (
        ("myaso-i-ptitsa", "Мясо и птица", "Говядина, курица, индейка"),
        ("ryba-i-moreprodukty", "Рыба и морепродукты", "Охлажденная рыба и морепродукты"),
        ("krupy-i-makarony", "Крупы и макароны", "Бакалея для гарниров"),
        ("konservy", "Консервы", "Овощные, рыбные и мясные консервы"),
        ("napitki", "Напитки", "Вода, соки и лимонады"),
        ("chai-i-kofe", "Чай и кофе", "Горячие напитки"),
        ("sladosti", "Сладости", "Шоколад, печенье и конфеты"),
        ("zamorozka", "Заморозка", "Замороженные продукты"),
        ("sousy-i-specii", "Соусы и специи", "Приправы и соусы"),
        ("detskoe-pitanie", "Детское питание", "Пюре, каши и смеси"),
        ("bytovaya-himiya", "Бытовая химия", "Средства для дома"),
        ("gigiena", "Гигиена", "Товары для ухода"),
    )
    product_names = (
        ("Куриное филе", "Фарш говяжий", "Индейка филе", "Голень куриная", "Стейк говяжий", "Котлеты домашние", "Бекон", "Сосиски молочные"),
        ("Лосось стейк", "Треска филе", "Креветки", "Скумбрия", "Сельдь", "Мидии", "Кальмар", "Форель"),
        ("Рис жасмин", "Гречка", "Овсяные хлопья", "Макароны спагетти", "Булгур", "Киноа", "Перловка", "Кускус"),
        ("Горошек", "Кукуруза", "Томаты резаные", "Тунец", "Фасоль красная", "Оливки", "Сардины", "Паштет"),
        ("Вода негазированная", "Вода газированная", "Сок яблочный", "Сок апельсиновый", "Морс", "Лимонад", "Квас", "Холодный чай"),
        ("Чай черный", "Чай зеленый", "Кофе зерновой", "Кофе молотый", "Какао", "Цикорий", "Капсулы кофе", "Травяной сбор"),
        ("Шоколад молочный", "Печенье овсяное", "Мармелад", "Вафли", "Конфеты ассорти", "Зефир", "Пряники", "Пирожное"),
        ("Пельмени", "Вареники", "Овощная смесь", "Пицца", "Наггетсы", "Блины", "Мороженое", "Ягоды замороженные"),
        ("Кетчуп", "Майонез", "Соевый соус", "Горчица", "Перец черный", "Паприка", "Карри", "Соль морская"),
        ("Пюре яблочное", "Пюре овощное", "Каша рисовая", "Смесь молочная", "Печенье детское", "Сок детский", "Творожок", "Вода детская"),
        ("Порошок стиральный", "Гель для стирки", "Средство для посуды", "Губки", "Пакеты мусорные", "Чистящий крем", "Кондиционер белья", "Салфетки"),
        ("Шампунь", "Гель для душа", "Мыло", "Зубная паста", "Щетка зубная", "Бумага туалетная", "Ватные диски", "Дезодорант"),
    )

    products: dict[str, Product] = {}
    for category_index, (slug, name, description) in enumerate(category_specs, start=10):
        upload = await get_or_create(
            session,
            Upload,
            stored_filename=f"seed/{slug}.jpg",
            defaults={
                "original_filename": f"{slug}.jpg",
                "mime_type": "image/jpeg",
                "size": 140000 + category_index,
                "storage_type": "local",
                "url": f"/uploads/seed/{slug}.jpg",
                "entity_type": "catalog",
                "uploaded_by": admin.id,
            },
        )
        category = await get_or_create(
            session,
            Category,
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "image_file_id": upload.id,
                "image_url": upload.url,
                "sort_order": category_index,
                "is_active": True,
                "sync_status": "synced",
                "external_1c_id": f"bulk-cat-{category_index:03}",
            },
        )
        for product_index, product_name in enumerate(product_names[category_index - 10], start=1):
            product_slug = f"{slug}-{product_index:02}"
            price = Decimal(69 + category_index * 9 + product_index * 13).quantize(Decimal("1.00"))
            old_price = price + Decimal("30.00") if product_index % 3 == 0 else None
            product_type = "weight" if category_index in (10, 11) and product_index <= 4 else "piece"
            product = await get_or_create(
                session,
                Product,
                slug=product_slug,
                defaults={
                    "category_id": category.id,
                    "name": product_name,
                    "article": f"BULK-{category_index:02}{product_index:02}",
                    "barcode": f"4610000{category_index:02}{product_index:02}",
                    "external_1c_id": f"bulk-product-{category_index:03}-{product_index:02}",
                    "sync_status": "synced",
                    "last_sync_at": NOW,
                    "source": "seed",
                    "description": f"{product_name}. Расширенный демо-каталог.",
                    "search_keywords": f"{product_name.lower()} {name.lower()}",
                    "preview_image_url": f"/uploads/seed/{product_slug}.jpg",
                    "unit": "кг" if product_type == "weight" else "шт",
                    "product_type": product_type,
                    "price": price,
                    "old_price": old_price,
                    "price_updated_at": NOW,
                    "stock_quantity": Decimal(15 + product_index * 7),
                    "stock_updated_at": NOW,
                    "quantity_step": Decimal("0.100") if product_type == "weight" else Decimal("1.000"),
                    "min_quantity": Decimal("0.500") if product_type == "weight" else Decimal("1.000"),
                    "low_stock_threshold": Decimal("5.000"),
                    "popularity": 250 - category_index * 5 - product_index,
                    "is_active": True,
                    "is_available": product_index != 8,
                },
            )
            products[product_slug] = product
            await get_or_create(
                session,
                ProductImage,
                product_id=product.id,
                url=f"/uploads/seed/{product_slug}.jpg",
                defaults={
                    "external_url": f"https://example.com/images/{product_slug}.jpg",
                    "sort_order": 1,
                    "is_main": True,
                },
            )
            await get_or_create(
                session,
                ProductPriceHistory,
                product_id=product.id,
                source="seed",
                defaults={"old_price": old_price or price, "new_price": price, "changed_at": NOW.replace(microsecond=0)},
            )
            await get_or_create(
                session,
                StockMovement,
                product_id=product.id,
                operation="income",
                reason="bulk seed initial stock",
                defaults={
                    "user_id": admin.id,
                    "quantity": product.stock_quantity,
                    "previous_stock_quantity": Decimal("0.000"),
                    "new_stock_quantity": product.stock_quantity,
                    "low_stock_threshold": product.low_stock_threshold,
                    "source": "seed",
                    "created_at": NOW,
                },
            )
    await session.flush()
    return products


async def seed_bulk_delivery(session: AsyncSession, admin: User) -> tuple[list[DeliveryZone], list[PickupPoint], list[DeliveryTimeSlot]]:
    zones = []
    for index, (name, city, price) in enumerate(
        (
            ("Север Москвы", "Москва", "249.00"),
            ("Юг Москвы", "Москва", "249.00"),
            ("Запад Москвы", "Москва", "299.00"),
            ("Восток Москвы", "Москва", "299.00"),
            ("Химки", "Химки", "349.00"),
            ("Мытищи", "Мытищи", "349.00"),
        ),
        start=1,
    ):
        zones.append(
            await get_or_create(
                session,
                DeliveryZone,
                name=name,
                city=city,
                defaults={
                    "description": f"Демо-зона доставки: {name}",
                    "price": Decimal(price),
                    "free_delivery_from": Decimal("4000.00"),
                    "min_order_amount": Decimal("900.00"),
                    "sort_order": index + 10,
                    "deleted_by": admin.id if index == 6 else None,
                },
            )
        )

    pickups = []
    for index, (name, city, address) in enumerate(
        (
            ("ПВЗ Арбат", "Москва", "ул. Арбат, 12"),
            ("ПВЗ Сокол", "Москва", "Ленинградский пр-т, 75"),
            ("ПВЗ Коломенская", "Москва", "пр-т Андропова, 20"),
            ("ПВЗ Химки", "Химки", "Юбилейный пр-т, 8"),
            ("ПВЗ Мытищи", "Мытищи", "ул. Мира, 30"),
        ),
        start=1,
    ):
        pickups.append(
            await get_or_create(
                session,
                PickupPoint,
                name=name,
                address=address,
                defaults={
                    "city": city,
                    "working_hours": "09:00-21:00",
                    "phone": f"+79990200{index:03}",
                    "latitude": Decimal("55.700000") + Decimal(index) / Decimal("1000"),
                    "longitude": Decimal("37.500000") + Decimal(index) / Decimal("1000"),
                    "sort_order": index + 10,
                },
            )
        )

    slots = []
    for index, (start_hour, end_hour) in enumerate(((9, 11), (11, 13), (13, 15), (15, 18), (18, 21)), start=1):
        slots.append(
            await get_or_create(
                session,
                DeliveryTimeSlot,
                delivery_type="delivery",
                label=f"{start_hour:02}:00-{end_hour:02}:00",
                defaults={
                    "pickup_point_id": None,
                    "start_time": time(start_hour, 0),
                    "end_time": time(end_hour, 0),
                    "orders_limit": 15,
                    "sort_order": index + 10,
                },
            )
        )
    await session.flush()
    return zones, pickups, slots


async def seed_bulk_marketing(
    session: AsyncSession,
    products: dict[str, Product],
) -> tuple[list[Discount], list[PromoCode]]:
    product_list = list(products.values())
    discounts = []
    for index, product in enumerate(product_list[:10], start=1):
        discount = await get_or_create(
            session,
            Discount,
            name=f"Демо-скидка {index}",
            defaults={
                "type": "catalog",
                "discount_type": "percent" if index % 2 else "fixed",
                "discount_value": Decimal("5.00") if index % 2 else Decimal("50.00"),
                "applicable_product_id": product.id,
                "starts_at": NOW - timedelta(days=index),
                "ends_at": NOW + timedelta(days=20 + index),
            },
        )
        discounts.append(discount)
        await get_or_create(session, DiscountProduct, discount_id=discount.id, product_id=product.id)

    promo_codes = []
    for index in range(1, 11):
        promo = await get_or_create(
            session,
            PromoCode,
            code=f"SEED{index:02}",
            defaults={
                "name": f"Демо-промокод {index}",
                "description": f"Промокод для демо-заказов #{index}",
                "discount_type": "percent" if index % 2 else "fixed",
                "discount_value": Decimal("7.00") if index % 2 else Decimal("100.00"),
                "min_order_amount": Decimal("800.00"),
                "max_discount_amount": Decimal("700.00"),
                "usage_limit": 500,
                "per_user_usage_limit": 3,
                "allow_discounted_products": True,
                "starts_at": NOW - timedelta(days=1),
                "ends_at": NOW + timedelta(days=90),
            },
        )
        promo_codes.append(promo)
        await get_or_create(session, PromoCodeProduct, promo_code_id=promo.id, product_id=product_list[index].id)
    await session.flush()
    return discounts, promo_codes


async def seed_bulk_customers_and_orders(
    session: AsyncSession,
    admin: User,
    products: dict[str, Product],
    zones: list[DeliveryZone],
    pickups: list[PickupPoint],
    slots: list[DeliveryTimeSlot],
    promo_codes: list[PromoCode],
) -> None:
    password_hash = PasswordService().hash_password(PASSWORD)
    product_list = list(products.values())
    statuses = ("created", "confirmed", "assembling", "delivering", "completed", "cancelled")
    payment_statuses = ("pending", "paid", "paid", "paid", "paid", "cancelled")
    customers = []

    for index in range(1, 41):
        customer = await get_or_create(
            session,
            User,
            phone=f"+79990100{index:03}",
            defaults={
                "name": f"Демо Покупатель {index}",
                "email": f"seed.customer{index:03}@example.com",
                "password_hash": password_hash,
                "role": UserRole.CUSTOMER,
                "is_active": True,
                "is_blocked": index % 19 == 0,
                "block_reason": "Демо-блокировка" if index % 19 == 0 else None,
            },
        )
        customers.append(customer)
        await get_or_create(
            session,
            Address,
            user_id=customer.id,
            title="Основной адрес",
            defaults={
                "city": zones[index % len(zones)].city,
                "street": f"Демо-улица {index}",
                "house": str(10 + index),
                "apartment": str(20 + index),
                "floor": str(index % 20 + 1),
                "comment": "Данные для демонстрации",
                "is_default": True,
            },
        )
        cart = await get_or_create(session, Cart, user_id=customer.id, defaults={"promo_code_id": promo_codes[index % len(promo_codes)].id})
        for offset in range(2):
            product = product_list[(index + offset) % len(product_list)]
            quantity = Decimal("1.000")
            await get_or_create(
                session,
                CartItem,
                cart_id=cart.id,
                product_id=product.id,
                defaults={
                    "name": product.name,
                    "quantity": quantity,
                    "unit": product.unit,
                    "price": product.price,
                    "total_price": product.price * quantity,
                },
            )
            await get_or_create(session, Favorite, user_id=customer.id, product_id=product.id)

    for index in range(1, 81):
        customer = customers[(index - 1) % len(customers)]
        zone = zones[index % len(zones)]
        pickup = pickups[index % len(pickups)]
        slot = slots[index % len(slots)]
        items = [product_list[(index + offset * 7) % len(product_list)] for offset in range(3)]
        quantities = [Decimal("1.000"), Decimal("2.000"), Decimal("1.500") if items[2].product_type == "weight" else Decimal("1.000")]
        subtotal = sum(product.price * quantity for product, quantity in zip(items, quantities, strict=True)).quantize(Decimal("1.00"))
        promo_discount = (subtotal * Decimal("0.05")).quantize(Decimal("1.00")) if index % 3 == 0 else Decimal("0.00")
        delivery_price = zone.price or Decimal("199.00")
        final_price = subtotal + delivery_price - promo_discount
        status = statuses[index % len(statuses)]
        payment_status = payment_statuses[index % len(payment_statuses)]
        address = await get_one(session, Address, user_id=customer.id, title="Основной адрес")

        order = await get_or_create(
            session,
            Order,
            order_number=f"SEED-{index + 1:04}",
            defaults={
                "user_id": customer.id,
                "address_id": address.id if address else None,
                "pickup_point_id": pickup.id if index % 4 == 0 else None,
                "delivery_zone_id": zone.id,
                "status": status,
                "payment_method": "card" if index % 2 else "cash",
                "payment_status": payment_status,
                "delivery_type": "pickup" if index % 4 == 0 else "delivery",
                "delivery_date": date.today() + timedelta(days=index % 7),
                "delivery_time_slot_id": slot.id,
                "delivery_price": delivery_price,
                "subtotal": subtotal,
                "discount_amount": Decimal("0.00"),
                "promo_discount_amount": promo_discount,
                "final_price": final_price,
                "customer_name": customer.name,
                "customer_phone": customer.phone,
                "customer_email": customer.email,
                "comment": f"Демо-заказ #{index}",
                "internal_comment": "Сгенерировано seed-скриптом",
                "cancel_reason": "Демо-отмена" if status == "cancelled" else None,
                "cancelled_at": NOW if status == "cancelled" else None,
                "cancelled_by": "customer" if status == "cancelled" else None,
                "cancelled_by_user_id": customer.id if status == "cancelled" else None,
                "sync_status": "synced" if index % 5 else "pending",
                "external_1c_id": f"1c-seed-order-{index:04}" if index % 5 else None,
                "last_sync_at": NOW if index % 5 else None,
                "items_count": len(items),
            },
        )

        for product, quantity in zip(items, quantities, strict=True):
            total = (product.price * quantity).quantize(Decimal("1.00"))
            await get_or_create(
                session,
                OrderItem,
                order_id=order.id,
                product_id=product.id,
                defaults={
                    "product_name": product.name,
                    "product_slug": product.slug,
                    "quantity": quantity,
                    "unit": product.unit,
                    "product_type": product.product_type,
                    "price": product.price,
                    "old_price": product.old_price,
                    "discount_amount": Decimal("0.00"),
                    "total_price": total,
                    "final_price": total,
                },
            )

        old_status = None
        for history_status in ("created", "confirmed", status):
            await get_or_create(
                session,
                OrderStatusHistory,
                order_id=order.id,
                status=history_status,
                defaults={"old_status": old_status, "comment": f"Статус: {history_status}", "changed_by": admin.id},
            )
            old_status = history_status

        if index % 3 == 0:
            promo_code = promo_codes[index % len(promo_codes)]
            await get_or_create(session, PromoCodeUsage, promo_code_id=promo_code.id, user_id=customer.id, order_id=order.id, defaults={"status": "applied"})

        provider_payment_id = f"seed-payment-{index + 1:04}"
        payment = await get_or_create(
            session,
            Payment,
            provider_payment_id=provider_payment_id,
            defaults={
                "order_id": order.id,
                "amount": final_price,
                "currency": "RUB",
                "status": payment_status,
                "provider": "yookassa" if index % 2 else "cash",
                "payment_url": f"https://payment.example.com/{provider_payment_id}",
                "paid_at": NOW - timedelta(days=index % 10) if payment_status == "paid" else None,
                "cancelled_at": NOW if payment_status == "cancelled" else None,
                "refund_status": "none",
            },
        )
        await get_or_create(
            session,
            PaymentWebhookLog,
            provider_event_id=f"seed-webhook-{index + 1:04}",
            defaults={
                "event_type": f"payment.{payment_status}",
                "provider_payment_id": provider_payment_id,
                "payment_id": payment.id,
                "payload": {"event": f"payment.{payment_status}", "order_number": order.order_number},
                "processing_status": "processed",
            },
        )
        await get_or_create(
            session,
            Notification,
            user_id=customer.id,
            title=f"Заказ {order.order_number}",
            defaults={
                "type": "order",
                "message": f"Статус заказа: {status}",
                "is_read": index % 2 == 0,
                "read_at": NOW if index % 2 == 0 else None,
            },
        )
        await get_or_create(
            session,
            NotificationLog,
            channel="email",
            recipient=customer.email,
            subject=f"Заказ {order.order_number}",
            defaults={"message": f"Статус заказа: {status}", "status": "sent", "created_by": admin.id},
        )
        await get_or_create(
            session,
            IntegrationLog,
            system="1c",
            entity_type="order",
            entity_id=order.id,
            action="export",
            defaults={
                "status": "success" if index % 5 else "failed",
                "request_payload": {"order_number": order.order_number},
                "response_payload": {"external_id": order.external_1c_id} if order.external_1c_id else None,
                "error_message": "Демо-ошибка синхронизации" if index % 5 == 0 else None,
            },
        )

    await get_or_create(
        session,
        IntegrationJob,
        type="bulk_seed_orders_export",
        started_by=admin.id,
        defaults={
            "status": "finished",
            "full_sync": True,
            "started_at": NOW - timedelta(minutes=15),
            "finished_at": NOW,
            "result_payload": {"orders_exported": 80, "products_created": len(product_list)},
        },
    )
    await session.flush()


async def seed_bulk_data(session: AsyncSession, users: dict[str, User]) -> None:
    products = await seed_bulk_catalog(session, users["admin"])
    zones, pickups, slots = await seed_bulk_delivery(session, users["admin"])
    _, promo_codes = await seed_bulk_marketing(session, products)
    await seed_bulk_customers_and_orders(session, users["admin"], products, zones, pickups, slots, promo_codes)


async def seed() -> None:
    async with db_helper.session_factory() as session:
        async with session.begin():
            users = await seed_users(session)
            await seed_settings(session)
            categories, products = await seed_catalog(session, users["admin"])
            zone, pickup, slot = await seed_delivery(session, users["admin"])
            _, promo_code = await seed_marketing(session, users["admin"], categories, products)
            order = await seed_customer_flow(session, users, products, promo_code, zone, pickup, slot)
            await seed_payments_and_logs(session, users, order)
            await seed_bulk_data(session, users)
    await db_helper.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
    print(f"Database seeded. Demo password for all users: {PASSWORD}")
