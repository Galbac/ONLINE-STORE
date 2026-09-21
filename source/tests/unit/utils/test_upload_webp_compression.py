import io
from PIL import Image

from source.utils.upload import convert_image_to_webp


def test_convert_jpeg_to_webp_compresses_and_returns_webp():
    # Создаем тестовое JPEG изображение
    img = Image.new("RGB", (800, 600), color=(120, 180, 70))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    jpeg_bytes = buf.getvalue()

    optimized_bytes, mime_type, extension = convert_image_to_webp(
        jpeg_bytes,
        original_content_type="image/jpeg",
        quality=80,
    )

    assert mime_type == "image/webp"
    assert extension == ".webp"
    assert len(optimized_bytes) < len(jpeg_bytes)

    # Проверяем, что результат открывается как валидный WEBP
    result_img = Image.open(io.BytesIO(optimized_bytes))
    assert result_img.format == "WEBP"
    assert result_img.size == (800, 600)


def test_convert_png_with_alpha_preserves_transparency():
    # Создаем PNG с прозрачностью (RGBA)
    img = Image.new("RGBA", (400, 400), color=(0, 200, 100, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    optimized_bytes, mime_type, extension = convert_image_to_webp(
        png_bytes,
        original_content_type="image/png",
        quality=82,
    )

    assert mime_type == "image/webp"
    assert extension == ".webp"

    result_img = Image.open(io.BytesIO(optimized_bytes))
    assert result_img.format == "WEBP"
    assert result_img.mode == "RGBA"


def test_oversized_image_downscaled_to_max_dimension():
    # Создаем огромное изображение 3000x2000
    img = Image.new("RGB", (3000, 2000), color=(50, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    huge_bytes = buf.getvalue()

    optimized_bytes, mime_type, extension = convert_image_to_webp(
        huge_bytes,
        original_content_type="image/jpeg",
        max_dimension=1920,
    )

    assert mime_type == "image/webp"
    assert extension == ".webp"

    result_img = Image.open(io.BytesIO(optimized_bytes))
    assert result_img.size[0] == 1920
    assert result_img.size[1] == 1280  # Сохранена пропорция 3:2


def test_critical_svg_format_is_preserved_without_webp_conversion():
    svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40"/></svg>'

    optimized_bytes, mime_type, extension = convert_image_to_webp(
        svg_bytes,
        original_content_type="image/svg+xml",
    )

    # SVG критичен для векторной графики — должен сохраниться как .svg
    assert mime_type == "image/svg+xml"
    assert extension == ".svg"
    assert optimized_bytes == svg_bytes
