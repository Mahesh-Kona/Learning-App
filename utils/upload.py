import base64
import uuid

from r2_client import s3, R2_BUCKET, CDN_BASE


def upload_base64_image_to_r2(base64_data: str, folder: str = "uploads") -> str:
    """Upload a base64-encoded image to Cloudflare R2 and return its CDN URL.

    This helper removes any leading data URL prefix, decodes the base64
    payload, stores it in the configured R2 bucket under the given folder,
    and returns the public CDN URL pointing to the stored object.
    """

    # remove data:image/...;base64,
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]

    file_bytes = base64.b64decode(base64_data)

    filename = f"{uuid.uuid4()}.jpg"
    r2_path = f"{folder}/{filename}"

    s3.put_object(
        Bucket=R2_BUCKET,
        Key=r2_path,
        Body=file_bytes,
        ContentType="image/jpeg",
    )

    return f"{CDN_BASE}/{r2_path}"
