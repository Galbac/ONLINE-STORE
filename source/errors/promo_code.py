class PromoCodeAlreadyExistsError(Exception):
    pass


class PromoCodeNotFoundError(Exception):
    pass


class EmptyPromoCodeUpdateError(Exception):
    pass


class PromoCodeUsageLimitExceededError(Exception):
    pass
