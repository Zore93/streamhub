"""Wasabi / S3-compatible storage uploader."""
import asyncio
import mimetypes
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config


def _client(settings: dict):
    return boto3.client(
        "s3",
        endpoint_url=settings.get("wasabi_endpoint") or "https://s3.wasabisys.com",
        aws_access_key_id=settings.get("wasabi_access_key"),
        aws_secret_access_key=settings.get("wasabi_secret_key"),
        region_name=settings.get("wasabi_region") or "us-east-1",
        config=Config(signature_version="s3v4"),
    )


def _public_url(settings: dict, key: str) -> str:
    base = settings.get("wasabi_public_base_url")
    if base:
        return f"{base.rstrip('/')}/{key}"
    endpoint = (settings.get("wasabi_endpoint") or "https://s3.wasabisys.com").rstrip("/")
    bucket = settings.get("wasabi_bucket", "")
    return f"{endpoint}/{bucket}/{key}"


def wasabi_configured(settings: dict) -> bool:
    return bool(
        settings.get("storage_backend") == "wasabi"
        and settings.get("wasabi_access_key")
        and settings.get("wasabi_secret_key")
        and settings.get("wasabi_bucket")
    )


async def upload_file(
    local_path: str, key: str, settings: dict, content_type: Optional[str] = None
) -> Optional[str]:
    """Uploads file to Wasabi; returns public URL or None on failure."""
    if not os.path.exists(local_path):
        return None
    if not content_type:
        content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"

    def _do():
        cli = _client(settings)
        cli.upload_file(
            local_path,
            settings["wasabi_bucket"],
            key,
            ExtraArgs={"ACL": "public-read", "ContentType": content_type},
        )

    try:
        await asyncio.to_thread(_do)
        return _public_url(settings, key)
    except Exception as e:  # noqa: BLE001
        print(f"[wasabi] upload failed for {key}: {e}")
        return None


async def test_connection(settings: dict) -> tuple[bool, str]:
    """Tries to head the bucket. Returns (ok, message)."""
    if not settings.get("wasabi_access_key"):
        return False, "Missing credentials"

    def _do():
        cli = _client(settings)
        cli.head_bucket(Bucket=settings.get("wasabi_bucket", ""))

    try:
        await asyncio.to_thread(_do)
        return True, "Connection OK"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def extract_key_from_public_url(url: str, settings: dict) -> Optional[str]:
    """Given a stored public Wasabi URL, return the object key (path inside bucket)."""
    bucket = settings.get("wasabi_bucket", "")
    if not bucket:
        return None
    # Match /bucket/<key>
    marker = f"/{bucket}/"
    if marker in url:
        return url.split(marker, 1)[1]
    # Match base URL: https://cdn.example.com/<key>
    base = (settings.get("wasabi_public_base_url") or "").rstrip("/")
    if base and url.startswith(base + "/"):
        return url[len(base) + 1:]
    return None


async def presign_get_url(
    public_url: str, settings: dict, ttl_seconds: int = 300
) -> Optional[str]:
    """Generate a short-lived presigned GET URL for a previously uploaded object."""
    key = extract_key_from_public_url(public_url, settings)
    if not key:
        return None

    def _do():
        cli = _client(settings)
        return cli.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings["wasabi_bucket"], "Key": key},
            ExpiresIn=int(ttl_seconds),
        )

    try:
        return await asyncio.to_thread(_do)
    except Exception as e:  # noqa: BLE001
        print(f"[wasabi] presign failed: {e}")
        return None
