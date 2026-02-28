import base64
import uuid
import re
from typing import Optional

from r2_client import s3, R2_BUCKET, CDN_BASE


def upload_base64_image_to_r2(base64_data: str, folder: str = "uploads", filename: Optional[str] = None) -> str:
    """Upload a base64-encoded image to Cloudflare R2 and return its CDN URL.

    This helper removes any leading data URL prefix, decodes the base64
    payload, stores it in the configured R2 bucket under the given folder,
    and returns the public CDN URL pointing to the stored object.
    """

    header = ""
    payload = base64_data

    # remove data:image/...;base64, prefix and capture header if present
    if "," in base64_data:
        header, payload = base64_data.split(",", 1)

    file_bytes = base64.b64decode(payload)

    # derive content type and default extension from header when possible
    content_type = "image/jpeg"
    ext = "jpg"
    if header.startswith("data:image"):
        m = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64", header)
        if m:
            content_type = m.group(1).lower()
            try:
                guessed_ext = content_type.split("/", 1)[1].lower()
                if guessed_ext == "jpeg":
                    guessed_ext = "jpg"
                ext = guessed_ext or ext
            except Exception:
                pass

    if filename:
        # If caller provided a name without extension, append inferred ext.
        if "." not in filename:
            filename = f"{filename}.{ext}"
    else:
        filename = f"{uuid.uuid4()}.{ext}"
    r2_path = f"{folder}/{filename}"

    s3.put_object(
        Bucket=R2_BUCKET,
        Key=r2_path,
        Body=file_bytes,
        ContentType=content_type,
    )

    return f"{CDN_BASE}/{r2_path}"