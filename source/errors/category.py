class CategoryNotFoundError(Exception):
    pass


class CategorySlugAlreadyExistsError(Exception):
    pass


class CategoryCycleError(Exception):
    pass


class CategoryHasActiveChildrenError(Exception):
    pass


class CategoryHasActiveProductsError(Exception):
    pass
