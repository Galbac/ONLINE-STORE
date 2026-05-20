class UserPhoneAlreadyExistsError(Exception):
    pass


class UserEmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AdminAuthAccessDeniedError(Exception):
    pass


class AdminAuthRateLimitExceededError(Exception):
    pass


class InactiveUserError(Exception):
    pass


class RefreshTokenNotFoundError(Exception):
    pass


class RefreshTokenAlreadyRevokedError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class InvalidRefreshTokenTypeError(Exception):
    pass


class RefreshTokenExpiredError(Exception):
    pass


class RefreshTokenRateLimitExceededError(Exception):
    pass


class RefreshTokenUserNotFoundError(Exception):
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


class AdminCurrentUserNotFoundError(Exception):
    pass


class AdminUserNotFoundError(Exception):
    pass


class AdminUserAlreadyBlockedError(Exception):
    pass


class AdminUserNotBlockedError(Exception):
    pass


class AdminStaffInvalidRoleError(Exception):
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


class OrderPrintFormatError(Exception):
    pass


class OrderItemsNotFoundError(Exception):
    pass


class RepeatOrderUnavailableError(Exception):
    pass


class CartProductNotFoundError(Exception):
    pass


class CartProductUnavailableError(Exception):
    pass


class CartInsufficientStockError(Exception):
    pass


class CartPieceQuantityMustBeIntegerError(Exception):
    pass


class CartQuantityStepError(Exception):
    pass


class CartQuantityBelowMinimumError(Exception):
    pass


class CartItemNotFoundError(Exception):
    pass


class CartItemAccessDeniedError(Exception):
    pass


class CartEmptyError(Exception):
    pass


class CartPromoCodeNotFoundError(Exception):
    pass


class CartPromoCodeInactiveError(Exception):
    pass


class CartPromoCodeExpiredError(Exception):
    pass


class CartPromoCodeLimitExceededError(Exception):
    pass


class CartPromoCodeAlreadyAppliedError(Exception):
    pass


class CartPromoCodeMinAmountError(Exception):
    pass


class CartPromoCodeNotApplicableError(Exception):
    pass


class OrderCartNotFoundError(Exception):
    pass


class OrderAddressRequiredError(Exception):
    pass


class OrderPickupPointRequiredError(Exception):
    pass


class OrderAddressNotFoundError(Exception):
    pass


class OrderAddressAccessDeniedError(Exception):
    pass


class OrderPickupPointNotFoundError(Exception):
    pass


class OrderPickupPointInactiveError(Exception):
    pass


class OrderUnavailableItemsError(Exception):
    def __init__(self, items: list) -> None:
        self.items = items


class OrderPromoCodeInvalidError(Exception):
    pass


class OrderAlreadyCancelledError(Exception):
    pass


class OrderCompletedCancellationError(Exception):
    pass


class OrderCancellationNotAllowedError(Exception):
    pass


class OneCIntegrationDisabledError(Exception):
    pass


class OrderAlreadySyncedError(Exception):
    pass


class OneCSyncError(Exception):
    pass


class OrderPaidCancellationRequiresManagerError(Exception):
    pass


class OrderPaymentMethodNotOnlineError(Exception):
    pass


class OrderAlreadyPaidError(Exception):
    pass


class OrderPaymentStatusNotAllowedError(Exception):
    pass


class OrderInvalidStatusError(Exception):
    pass


class OrderStatusTransitionError(Exception):
    pass


class EmptyOrderUpdateError(Exception):
    pass


class OrderFieldNotEditableError(Exception):
    pass


class OrderUpdateNotAllowedError(Exception):
    pass


class OrderConfirmNotAllowedError(Exception):
    pass


class PaymentProviderCreateError(Exception):
    pass


class PaymentNotFoundError(Exception):
    pass


class PaymentAccessDeniedError(Exception):
    pass


class PaymentConfirmationNotSupportedError(Exception):
    pass


class PaymentConfirmationStatusNotAllowedError(Exception):
    pass


class PaymentAlreadyConfirmedError(Exception):
    pass


class PaymentProviderConfirmError(Exception):
    pass


class InvalidPaymentWebhookSignatureError(Exception):
    pass


class InvalidPaymentWebhookPayloadError(Exception):
    pass


class PaymentCancellationStatusNotAllowedError(Exception):
    pass


class PaymentAlreadyPaidError(Exception):
    pass


class PaymentProviderCancelError(Exception):
    pass


class RefundAccessDeniedError(Exception):
    pass


class PaymentNotPaidError(Exception):
    pass


class InvalidRefundAmountError(Exception):
    pass


class RefundAmountExceedsAvailableError(Exception):
    pass


class PaymentProviderRefundError(Exception):
    pass
