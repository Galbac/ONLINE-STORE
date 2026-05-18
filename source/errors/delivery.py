class DeliveryDisabledError(Exception):
    pass


class DeliveryMinOrderAmountError(Exception):
    pass


class DeliveryAddressNotFoundError(Exception):
    pass


class DeliveryAddressAccessDeniedError(Exception):
    pass
