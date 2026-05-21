class DiscountNotFoundError(Exception):
    pass


class EmptyDiscountUpdateError(Exception):
    pass


class DiscountConflictError(Exception):
    pass


class DiscountExpiredError(Exception):
    pass
