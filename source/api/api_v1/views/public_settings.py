from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.repositories.settings import SettingsRepository
from source.schemas.pydantic.public_settings import PublicStoreSettingsResponse
from source.schemas.pydantic.settings import DayScheduleItem
from source.utils.schedule import calculate_schedule_status, format_schedule_summary, normalize_schedule

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=PublicStoreSettingsResponse, status_code=status.HTTP_200_OK)
@inject
async def get_public_store_settings(
    session: FromDishka[AsyncSession] = None,
    settings_repository: FromDishka[SettingsRepository] = None,
) -> PublicStoreSettingsResponse:
    store_settings, _ = await settings_repository.get_or_create_default(session=session)
    raw_schedule = getattr(store_settings, "schedule", None)
    normalized_sched = normalize_schedule(raw_schedule)
    maintenance = getattr(store_settings, "maintenance_mode", False)
    is_open_now, current_status_text = calculate_schedule_status(
        normalized_sched,
        maintenance_mode=maintenance,
    )
    schedule_items = [
        DayScheduleItem(
            day=item["day"],
            day_name=item["day_name"],
            is_day_off=item["is_day_off"],
            open_time=item.get("open_time"),
            close_time=item.get("close_time"),
        )
        for item in normalized_sched
    ]
    working_hours = getattr(store_settings, "working_hours", None) or format_schedule_summary(normalized_sched)

    return PublicStoreSettingsResponse(
        shop_name=store_settings.shop_name,
        legal_name=store_settings.legal_name,
        inn=store_settings.inn,
        ogrn=store_settings.ogrn,
        phone=store_settings.phone,
        email=store_settings.email,
        address=store_settings.address,
        working_hours=working_hours,
        schedule=schedule_items,
        is_open_now=is_open_now,
        current_status_text=current_status_text,
        online_payment_enabled=bool(store_settings.online_payment_enabled) if store_settings.online_payment_enabled is not None else True,
        pay_on_delivery_enabled=bool(store_settings.pay_on_delivery_enabled) if store_settings.pay_on_delivery_enabled is not None else True,
        maintenance_mode=bool(store_settings.maintenance_mode) if store_settings.maintenance_mode is not None else False,
        promo_codes_enabled=bool(store_settings.promo_codes_enabled) if store_settings.promo_codes_enabled is not None else True,
        referral_program_enabled=bool(store_settings.referral_program_enabled) if store_settings.referral_program_enabled is not None else True,
        loyalty_program_enabled=bool(store_settings.loyalty_program_enabled) if store_settings.loyalty_program_enabled is not None else True,
        privacy_policy_url=store_settings.privacy_policy_url,
        user_agreement_url=store_settings.user_agreement_url,
        personal_data_consent_url=store_settings.personal_data_consent_url,
    )
