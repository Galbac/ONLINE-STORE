from pydantic import BaseModel


class PublicStoreSettingsResponse(BaseModel):
    shop_name: str
    legal_name: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    working_hours: str | None = None
    online_payment_enabled: bool = True
    pay_on_delivery_enabled: bool = True
    maintenance_mode: bool = False
    promo_codes_enabled: bool = True
    referral_program_enabled: bool = True
    loyalty_program_enabled: bool = True
    privacy_policy_url: str | None = None
    user_agreement_url: str | None = None
    personal_data_consent_url: str | None = None
