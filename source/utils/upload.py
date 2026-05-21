from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from source.errors.upload import (
    UploadFileMissingError,
    UploadFileTooLargeError,
    UploadInvalidImageError,
    UploadUnsupportedExtensionError,
    UploadUnsupportedFormatError,
)


_ALLOWED_EXTENSIONS_BY_MIME_TYPE = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


def get_file_extension(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


def generate_safe_filename(*, extension: str, entity_type: str | None) -> str:
    directory = entity_type or "other"
    return f"{directory}/{uuid4().hex}{extension}"


def validate_file_extension(
    *,
    filename: str | None,
    content_type: str,
    allowed_extensions: set[str],
) -> str:
    if not filename or Path(filename).name != filename:
        raise UploadFileMissingError

    extension = get_file_extension(filename)
    if extension not in allowed_extensions:
        raise UploadUnsupportedExtensionError
    if extension not in _ALLOWED_EXTENSIONS_BY_MIME_TYPE.get(content_type, set()):
        raise UploadUnsupportedExtensionError
    return extension


def validate_file_size(*, content: bytes, max_size_bytes: int) -> None:
    if not content:
        raise UploadFileMissingError
    if len(content) > max_size_bytes:
        raise UploadFileTooLargeError


def detect_mime_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


async def validate_image_file(
    *,
    file: UploadFile | None,
    allowed_mime_types: set[str],
    allowed_extensions: set[str] | None = None,
    max_size_bytes: int,
) -> bytes:
    if file is None or file.filename is None:
        raise UploadFileMissingError
    if file.content_type not in allowed_mime_types:
        raise UploadUnsupportedFormatError

    validate_file_extension(
        filename=file.filename,
        content_type=file.content_type,
        allowed_extensions=allowed_extensions or set().union(*_ALLOWED_EXTENSIONS_BY_MIME_TYPE.values()),
    )

    content = await file.read()
    validate_file_size(content=content, max_size_bytes=max_size_bytes)
    detected_mime_type = detect_mime_type(content)
    if detected_mime_type is None or detected_mime_type != file.content_type:
        raise UploadInvalidImageError
    return content
