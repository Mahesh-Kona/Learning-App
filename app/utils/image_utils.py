import base64
import io
from typing import Any

from PIL import Image


def _compress_base64_image_string(value: str, scale_factor: float = 0.8) -> str:
    if not value or not isinstance(value, str):
        return value

    header = ""
    b64_data = value

    if value.startswith("data:image") and "," in value:
        header, b64_data = value.split(",", 1)

    try:
        original_bytes = base64.b64decode(b64_data)
    except Exception:
        return value

    try:
        with Image.open(io.BytesIO(original_bytes)) as img:
            width, height = img.size
            if width <= 0 or height <= 0:
                return value

            new_width = max(1, int(width * scale_factor))
            new_height = max(1, int(height * scale_factor))

            resized = img.resize((new_width, new_height), Image.LANCZOS)

            output = io.BytesIO()

            format_ = (img.format or "PNG").upper()
            save_kwargs = {}

            if format_ in {"JPEG", "JPG"}:
                save_kwargs["format"] = "JPEG"
                save_kwargs["quality"] = 70
                save_kwargs["optimize"] = True
            elif format_ == "WEBP":
                save_kwargs["format"] = "WEBP"
                save_kwargs["quality"] = 70
            else:
                save_kwargs["format"] = format_
                save_kwargs["optimize"] = True

            resized.save(output, **save_kwargs)
            compressed_bytes = output.getvalue()

            compressed_b64 = base64.b64encode(compressed_bytes).decode("ascii")

            if header:
                return f"{header},{compressed_b64}"
            return compressed_b64
    except Exception:
        return value


def _looks_like_base64_image(value: str) -> bool:
    if not isinstance(value, str):
        return False

    if value.startswith("data:image"):
        return True

    if len(value) < 1024:
        return False

    try:
        base64.b64decode(value, validate=True)
        return True
    except Exception:
        return False


def compress_images_in_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: compress_images_in_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [compress_images_in_json(v) for v in data]

    if isinstance(data, str) and _looks_like_base64_image(data):
        return _compress_base64_image_string(data)

    return data
