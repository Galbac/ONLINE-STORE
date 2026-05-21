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


class EmptyDeliverySettingsUpdateError(Exception):
    pass


class DeliveryZoneAlreadyExistsError(Exception):
    pass


class DeliveryZoneNotFoundError(Exception):
    pass


class EmptyDeliveryZoneUpdateError(Exception):
    pass


class DeliveryZoneActiveOrdersError(Exception):
    pass


class PickupPointAlreadyExistsError(Exception):
    pass


class PickupPointAdminNotFoundError(Exception):
    pass


class EmptyPickupPointUpdateError(Exception):
    pass


class PickupPointActiveOrdersError(Exception):
    pass
