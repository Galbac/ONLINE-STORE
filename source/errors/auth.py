class UserPhoneAlreadyExistsError(Exception):
    pass


class UserEmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass


class RefreshTokenNotFoundError(Exception):
    pass


class RefreshTokenAlreadyRevokedError(Exception):
    pass


class PasswordResetRateLimitExceededError(Exception):
    pass


class InvalidPasswordResetTokenError(Exception):
    pass


class PasswordResetUserNotFoundError(Exception):
    pass


class NewPasswordSameAsOldError(Exception):
    pass


class InvalidCurrentPasswordError(Exception):
    pass


class ChangePasswordRateLimitExceededError(Exception):
    pass


class CurrentUserNotFoundError(Exception):
    pass


class EmptyUserProfileUpdateError(Exception):
    pass


class UserDeleteConfirmationRequiredError(Exception):
    pass


class ActiveOrdersExistError(Exception):
    pass


class UserAddressesLimitExceededError(Exception):
    pass


class AddressNotFoundError(Exception):
    pass


class AddressAccessDeniedError(Exception):
    pass


class AddressActiveOrderExistsError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class OrderAccessDeniedError(Exception):
    pass


class OrderItemsNotFoundError(Exception):
    pass


class RepeatOrderUnavailableError(Exception):
    pass
