class NotificationNotFoundError(Exception):
    pass


class NotificationAccessDeniedError(Exception):
    pass


class NotificationEmailDisabledError(Exception):
    pass


class NotificationTelegramDisabledError(Exception):
    pass


class NotificationTelegramChatIdMissingError(Exception):
    pass


class NotificationSendError(Exception):
    pass
