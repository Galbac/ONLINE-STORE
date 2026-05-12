class UserPhoneAlreadyExistsError(Exception):
    pass


class UserEmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass
