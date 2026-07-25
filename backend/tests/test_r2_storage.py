"""Tests for backend/adapters/r2_storage.py (SS-011), mocked ``boto3`` client.

A real, live-verified round-trip against the actual `stylesense-media`
bucket was also performed during this ticket's Developer phase (put/get/
delete all worked with real CLOUDFLARE_R2_* credentials, then cleaned up) --
see docs/worklog/SS-011.md. These tests cover the adapter's call shape with
a fake client, so they run without real credentials/network in CI.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from adapters.r2_storage import R2StorageClient


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def test_get_object_bytes_calls_get_object_with_exact_bucket_and_key_and_returns_body() -> None:
    fake_client = MagicMock()
    fake_client.get_object.return_value = {"Body": _FakeBody(b"clean-image-bytes")}

    storage = R2StorageClient(bucket="stylesense-media", client=fake_client)
    result = storage.get_object_bytes("wardrobe/user-1/item-1/original.jpg")

    fake_client.get_object.assert_called_once_with(
        Bucket="stylesense-media", Key="wardrobe/user-1/item-1/original.jpg"
    )
    assert result == b"clean-image-bytes"


def test_put_object_bytes_calls_put_object_with_exact_bucket_key_and_content_type() -> None:
    fake_client = MagicMock()

    storage = R2StorageClient(bucket="stylesense-media", client=fake_client)
    storage.put_object_bytes("wardrobe/user-1/item-1/clean.png", b"png-bytes", "image/png")

    fake_client.put_object.assert_called_once_with(
        Bucket="stylesense-media",
        Key="wardrobe/user-1/item-1/clean.png",
        Body=b"png-bytes",
        ContentType="image/png",
    )


def test_constructor_uses_injected_bucket_and_client_without_touching_env(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("CLOUDFLARE_R2_BUCKET", raising=False)
    monkeypatch.delenv("CLOUDFLARE_R2_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_R2_ACCESS_KEY", raising=False)
    monkeypatch.delenv("CLOUDFLARE_R2_SECRET_KEY", raising=False)

    fake_client = MagicMock()
    # Should not raise despite no env vars set, since bucket/client are
    # both injected explicitly.
    storage = R2StorageClient(bucket="explicit-bucket", client=fake_client)

    assert storage._bucket == "explicit-bucket"
    assert storage._client is fake_client
