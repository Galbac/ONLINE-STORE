from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from source.errors.upload import UploadFileMissingError, UploadFileTooLargeError, UploadUnsupportedFormatError


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


async def validate_image_file(
    *,
    file: UploadFile | None,
    allowed_mime_types: set[str],
    max_size_bytes: int,
) -> bytes:
    if file is None or file.filename is None:
        raise UploadFileMissingError
    if file.content_type not in allowed_mime_types:
        raise UploadUnsupportedFormatError

    extension = get_file_extension(file.filename)
    if extension not in _ALLOWED_EXTENSIONS_BY_MIME_TYPE.get(file.content_type, set()):
        raise UploadUnsupportedFormatError

    content = await file.read()
    if len(content) > max_size_bytes:
        raise UploadFileTooLargeError
    if not content:
        raise UploadFileMissingError
    return content
