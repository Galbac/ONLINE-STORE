class ProductNotFoundError(Exception):
    pass


class ProductSlugAlreadyExistsError(Exception):
    pass


class ProductSkuAlreadyExistsError(Exception):
    pass


class ProductBarcodeAlreadyExistsError(Exception):
    pass
