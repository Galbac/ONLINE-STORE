class UploadFileMissingError(Exception):
    pass


class UploadUnsupportedFormatError(Exception):
    pass


class UploadUnsupportedExtensionError(Exception):
    pass


class UploadFileTooLargeError(Exception):
    pass


class UploadInvalidImageError(Exception):
    pass


class UploadStorageError(Exception):
    pass


class UploadNotFoundError(Exception):
    pass


class UploadInUseError(Exception):
    pass


class UploadPrivateAccessRequiredError(Exception):
    pass


class UploadAccessDeniedError(Exception):
    pass
