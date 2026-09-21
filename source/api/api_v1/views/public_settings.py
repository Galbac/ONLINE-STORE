from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.repositories.settings import SettingsRepository
from source.schemas.pydantic.public_settings import PublicStoreSettingsResponse

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=PublicStoreSettingsResponse, status_code=status.HTTP_200_OK)
@inject
async def get_public_store_settings(
    session: FromDishka[AsyncSession] = None,
    settings_repository: FromDishka[SettingsRepository] = None,
) -> PublicStoreSettingsResponse:
    store_settings, _ = await settings_repository.get_or_create_default(session=session)
    return PublicStoreSettingsResponse(
        shop_name=store_settings.shop_name,
        legal_name=store_settings.legal_name,
        inn=store_settings.inn,
        ogrn=store_settings.ogrn,
        phone=store_settings.phone,
        email=store_settings.email,
        address=store_settings.address,
        working_hours=store_settings.working_hours,
        online_payment_enabled=store_settings.online_payment_enabled,
        pay_on_delivery_enabled=store_settings.pay_on_delivery_enabled,
        maintenance_mode=store_settings.maintenance_mode,
        promo_codes_enabled=store_settings.promo_codes_enabled,
        referral_program_enabled=store_settings.referral_program_enabled,
        loyalty_program_enabled=store_settings.loyalty_program_enabled,
        privacy_policy_url=store_settings.privacy_policy_url,
        user_agreement_url=store_settings.user_agreement_url,
        personal_data_consent_url=store_settings.personal_data_consent_url,
    )
