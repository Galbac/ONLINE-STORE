class CategoryNotFoundError(Exception):
    pass


class CategorySlugAlreadyExistsError(Exception):
    pass


class CategoryCycleError(Exception):
    pass
