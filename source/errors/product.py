class ProductNotFoundError(Exception):
    pass


class ProductSlugAlreadyExistsError(Exception):
    pass


class ProductSkuAlreadyExistsError(Exception):
    pass


class ProductBarcodeAlreadyExistsError(Exception):
    pass


class ProductActiveOrderExistsError(Exception):
    pass


class ProductImageNotFoundError(Exception):
    pass


class ProductImageOwnershipError(Exception):
    pass
