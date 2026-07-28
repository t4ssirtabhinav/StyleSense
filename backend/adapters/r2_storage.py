"""Thin ``boto3`` S3-compatible client wrapper for direct, server-side R2
reads/writes (SS-011).

Entirely separate from SS-010's presigned-URL mechanism -- this is a
**direct, non-presigned** write using the real ``CLOUDFLARE_R2_ACCESS_KEY``/
``SECRET_KEY`` (the backend holds real credentials, unlike the mobile
client), so ``BL-051``'s "R2 does not support presigned POST" finding does
not apply here at all (different mechanism).

Live-verified 2026-07-24 against the real ``stylesense-media`` bucket during
this ticket's Developer phase: ``put_object`` / ``get_object`` /
``delete_object`` all round-tripped correctly with real
``CLOUDFLARE_R2_*`` credentials (test object written, read back byte-for-byte
identical, then deleted -- confirmed gone via a subsequent ``get_object``
raising ``NoSuchKey``). See docs/worklog/SS-011.md for the full note.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.config import Config


def _build_client() -> Any:  # noqa: ANN401 - boto3 has no exported S3 client type
    account_id = os.environ["CLOUDFLARE_R2_ACCOUNT_ID"]
    access_key = os.environ["CLOUDFLARE_R2_ACCESS_KEY"]
    secret_key = os.environ["CLOUDFLARE_R2_SECRET_KEY"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


class R2StorageClient:
    """Wraps the bucket name + boto3 client so callers never touch either
    directly (single injection point, easy to fake in tests). Both methods
    are synchronous (``boto3`` has no native async client) -- the caller
    (``WardrobeBgRemovalService``) is responsible for offloading these to a
    thread (``asyncio.to_thread``) so they don't block the event loop."""

    def __init__(self, bucket: str | None = None, client: Any | None = None) -> None:
        self._bucket = bucket or os.environ["CLOUDFLARE_R2_BUCKET"]
        self._client = client or _build_client()

    def get_object_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body: bytes = response["Body"].read()
        return body

    def put_object_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def delete_objects(self, keys: list[str]) -> None:
        """SS-015 -- batch delete for item-delete's R2 cleanup. Synchronous
        like every other method on this class; the caller
        (WardrobeDeletionService) offloads via ``asyncio.to_thread``. A
        no-op on an empty list (boto3's ``delete_objects`` requires at
        least one key)."""
        if not keys:
            return
        self._client.delete_objects(
            Bucket=self._bucket,
            Delete={"Objects": [{"Key": key} for key in keys]},
        )

    def generate_presigned_get_url(self, key: str, expiry_seconds: int) -> str:
        """SS-013's read-path (`GET /wardrobe/items/{id}/image-url`) --
        boto3's `generate_presigned_url` is a local signature computation,
        not a network call, so this stays synchronous like the two methods
        above (no `asyncio.to_thread` needed here either)."""
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiry_seconds,
        )
        return url
