class DeliveryDisabledError(Exception):
    pass


class DeliveryMinOrderAmountError(Exception):
    pass


class DeliveryAddressNotFoundError(Exception):
    pass


class DeliveryAddressAccessDeniedError(Exception):
    pass


class PickupPointNotFoundError(Exception):
    pass


class PickupPointInactiveError(Exception):
    pass


class PickupDisabledError(Exception):
    pass


class DeliveryDateInPastError(Exception):
    pass


class DeliveryTimeSlotUnavailableError(Exception):
    pass
