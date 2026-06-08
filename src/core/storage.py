import os
import uuid
import shutil
import logging
from pathlib import Path
from fastapi import UploadFile
from src.core.config import settings

logger = logging.getLogger(__name__)

# Local storage directory
LOCAL_UPLOAD_DIR = Path("uploads")
LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)


def _local_save(file: UploadFile, subfolder: str) -> str:
    """Saves file locally. Returns the public URL path."""
    folder = LOCAL_UPLOAD_DIR / subfolder
    folder.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "file").suffix.lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = folder / filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Return a URL path the frontend can use
    return f"{settings.api_base_url}/uploads/{subfolder}/{filename}"


async def _s3_save(file: UploadFile, subfolder: str) -> str:
    """Saves file to S3/MinIO. Returns the public URL."""
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        ext = Path(file.filename or "file").suffix.lower()
        key = f"{subfolder}/{uuid.uuid4().hex}{ext}"
        file.file.seek(0)
        s3.upload_fileobj(
            file.file,
            settings.s3_bucket,
            key,
            ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
        )
        if settings.s3_public_url:
            return f"{settings.s3_public_url}/{key}"
        return f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        raise


async def save_file(file: UploadFile, subfolder: str = "misc") -> str:
    """
    Unified file save — uses S3 in production, local disk in dev.
    Returns the public URL of the saved file.
    """
    allowed_image_types = {
        "image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"
    }
    if file.content_type and file.content_type not in allowed_image_types:
        raise ValueError(
            f"File type '{file.content_type}' not allowed. "
            f"Allowed: JPEG, PNG, WebP, GIF, SVG"
        )

    # File size limit: 5MB
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > 5 * 1024 * 1024:
        raise ValueError("File size exceeds 5MB limit")

    if settings.s3_bucket and settings.s3_access_key:
        return await _s3_save(file, subfolder)
    else:
        return _local_save(file, subfolder)