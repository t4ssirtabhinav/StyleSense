"""Tests for backend/services/wardrobe_bg_removal_service.py (SS-011)."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

import pytest
from PIL import Image

from adapters.interfaces import IWardrobeRepository
from ai.ports.interfaces import BackgroundRemovalResult, IBackgroundRemovalProvider
from services.circuit_breaker import CircuitBreaker
from services.image_processing import resize_for_bg_removal
from services.wardrobe_bg_removal_service import (
    WardrobeBgRemovalService,
    clean_image_key,
    thumbnail_image_key,
)


def _jpeg_bytes(
    color: tuple[int, int, int] = (20, 40, 60), size: tuple[int, int] = (100, 100)
) -> bytes:
    image = Image.new("RGB", size, color)
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def _white_jpeg_bytes() -> bytes:
    return _jpeg_bytes((255, 255, 255))


def _png_with_alpha(alpha: int = 255, size: tuple[int, int] = (100, 100)) -> bytes:
    image = Image.new("RGBA", size, (10, 20, 30, alpha))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class _FakeProvider(IBackgroundRemovalProvider):
    def __init__(
        self, results: list[BackgroundRemovalResult] | None = None, delay: float = 0.0
    ) -> None:
        self.calls = 0
        self.max_concurrent = 0
        self._current_concurrent = 0
        self._results = results
        self._delay = delay
        self.received_image_bytes: list[bytes] = []

    async def remove_background(self, image_bytes: bytes) -> BackgroundRemovalResult:
        self.received_image_bytes.append(image_bytes)
        self._current_concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self._current_concurrent)
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        self._current_concurrent -= 1

        if self._results:
            return self._results.pop(0)
        return BackgroundRemovalResult(success=True, image_bytes=_png_with_alpha(), latency_ms=50)


class _FakeRepository(IWardrobeRepository):
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    async def upsert_uploaded_row(
        self, *, jwt: str, item_id: str, user_id: str, image_key: str
    ) -> None:
        self.upserts.append(
            {"jwt": jwt, "item_id": item_id, "user_id": user_id, "image_key": image_key}
        )

    async def update_bg_removal_result(
        self,
        *,
        jwt: str,
        item_id: str,
        processing_status: str,
        image_clean_url: str | None,
        thumbnail_url: str | None,
        bg_removal_tags: dict[str, Any],
    ) -> None:
        self.updates.append(
            {
                "jwt": jwt,
                "item_id": item_id,
                "processing_status": processing_status,
                "image_clean_url": image_clean_url,
                "thumbnail_url": thumbnail_url,
                "bg_removal_tags": bg_removal_tags,
            }
        )

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        return "free"


class _FakeStorage:
    def __init__(self, original_bytes: bytes, fail_put: bool = False) -> None:
        self._original_bytes = original_bytes
        self._fail_put = fail_put
        self.puts: list[tuple[str, bytes, str]] = []

    def get_object_bytes(self, key: str) -> bytes:
        return self._original_bytes

    def put_object_bytes(self, key: str, data: bytes, content_type: str) -> None:
        if self._fail_put:
            raise RuntimeError("R2 write failed")
        self.puts.append((key, data, content_type))


class _FakeCircuitBreaker:
    def __init__(self, open_: bool = False) -> None:
        self._open = open_
        self.failures_recorded = 0
        self.successes_recorded = 0

    async def is_open(self) -> bool:
        return self._open

    async def record_failure(self) -> None:
        self.failures_recorded += 1

    async def record_success(self) -> None:
        self.successes_recorded += 1


async def test_happy_path_uploads_clean_and_thumbnail_and_marks_bg_removed() -> None:
    # Original wider than the 800px proxy default, so we can distinguish
    # "provider received the full-resolution original" (wrong, post-QA
    # amendment) from "provider received the downscaled proxy" (right).
    original_bytes = _jpeg_bytes(size=(1200, 800))
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(original_bytes)
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)  # type: ignore[arg-type]
    await service.process(jwt="jwt", user_id="user-1", item_id="item-1")

    assert provider.calls == 1
    # Post-QA amendment: the provider must receive the resize_for_bg_removal
    # proxy, not the full-resolution original bytes verbatim.
    expected_proxy_bytes = resize_for_bg_removal(original_bytes)
    assert provider.received_image_bytes[0] == expected_proxy_bytes
    assert provider.received_image_bytes[0] != original_bytes
    with Image.open(io.BytesIO(provider.received_image_bytes[0])) as proxy:
        assert proxy.width == 800

    assert len(storage.puts) == 2
    put_keys = {key for key, _, _ in storage.puts}
    assert put_keys == {
        clean_image_key("user-1", "item-1"),
        thumbnail_image_key("user-1", "item-1"),
    }

    # The stored clean.png must be composited back to the *original's*
    # full resolution, not left at the proxy's smaller resolution.
    clean_bytes = next(data for key, data, _ in storage.puts if key == clean_image_key("user-1", "item-1"))
    with Image.open(io.BytesIO(clean_bytes)) as clean_image:
        assert clean_image.mode == "RGBA"
        assert clean_image.size == (1200, 800)

    assert len(repository.updates) == 1
    update = repository.updates[0]
    assert update["processing_status"] == "bg_removed"
    assert update["image_clean_url"] == clean_image_key("user-1", "item-1")
    assert update["thumbnail_url"] == thumbnail_image_key("user-1", "item-1")
    assert update["bg_removal_tags"]["source"] == "replicate"


async def test_already_transparent_input_skips_provider_call_and_still_marks_bg_removed() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_white_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)  # type: ignore[arg-type]
    await service.process(jwt="jwt", user_id="user-1", item_id="item-1")

    assert provider.calls == 0
    assert len(repository.updates) == 1
    update = repository.updates[0]
    assert update["processing_status"] == "bg_removed"
    assert update["bg_removal_tags"]["source"] == "skipped_already_transparent"


async def test_circuit_open_skips_provider_marks_bg_pending_no_cost() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker(open_=True)

    service = WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)  # type: ignore[arg-type]
    await service.process(jwt="jwt", user_id="user-1", item_id="item-1")

    assert provider.calls == 0
    assert len(repository.updates) == 1
    update = repository.updates[0]
    assert update["processing_status"] == "bg_pending"
    assert update["bg_removal_tags"]["source"] == "circuit_open"


async def test_provider_failure_not_yet_third_marks_bg_pending_records_one_failure() -> None:
    provider = _FakeProvider(results=[BackgroundRemovalResult(success=False, error="boom")])
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)  # type: ignore[arg-type]
    await service.process(jwt="jwt", user_id="user-1", item_id="item-1")

    assert circuit_breaker.failures_recorded == 1
    assert repository.updates[0]["processing_status"] == "bg_pending"


async def test_third_consecutive_failure_opens_real_circuit_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration-style: a real CircuitBreaker instance backed by a fake
    in-memory Upstash, verifying the service calls record_failure() enough
    times to actually open it."""
    import httpx

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    store: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        path = url.split("://", 1)[1].split("/", 1)[1]
        segments = path.split("/")
        if segments[0] == "get":
            return httpx.Response(200, json={"result": store.get(segments[1])}, request=request)
        if segments[0] == "incr":
            store[segments[1]] = int(store.get(segments[1], 0)) + 1
            return httpx.Response(200, json={"result": store[segments[1]]}, request=request)
        if segments[0] == "set":
            store[segments[1]] = segments[2]
            return httpx.Response(200, json={"result": "OK"}, request=request)
        raise AssertionError(url)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    real_circuit_breaker = CircuitBreaker(failure_threshold=3, open_seconds=60)
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())

    for _ in range(3):
        provider = _FakeProvider(results=[BackgroundRemovalResult(success=False, error="boom")])
        service = WardrobeBgRemovalService(provider, repository, storage, real_circuit_breaker)  # type: ignore[arg-type]
        await service.process(jwt="jwt", user_id="user-1", item_id="item-1")

    assert await real_circuit_breaker.is_open() is True


async def test_r2_upload_failure_after_successful_provider_call_marks_bg_pending_but_logs_cost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes(), fail_put=True)
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO):
        await service.process(jwt="jwt", user_id="user-1", item_id="item-1")

    assert repository.updates[0]["processing_status"] == "bg_pending"
    ai_call_records = [r for r in caplog.records if r.message == "ai_call"]
    assert len(ai_call_records) == 1
    assert ai_call_records[0].cost_usd == 0.0023  # type: ignore[attr-defined]


async def test_semaphore_caps_concurrency_at_three_for_ten_parallel_calls() -> None:
    provider = _FakeProvider(delay=0.05)
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(
        provider,
        repository,
        storage,  # type: ignore[arg-type]
        circuit_breaker,  # type: ignore[arg-type]
        max_concurrent_replicate_calls=3,
    )

    await asyncio.gather(
        *(service.process(jwt="jwt", user_id="user-1", item_id=f"item-{i}") for i in range(10))
    )

    assert provider.calls == 10
    assert provider.max_concurrent <= 3


async def test_successful_real_call_logs_user_id_cost_and_latency(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO):
        await service.process(jwt="jwt", user_id="user-42", item_id="item-1")

    ai_call_records = [r for r in caplog.records if r.message == "ai_call"]
    assert len(ai_call_records) == 1
    record = ai_call_records[0]
    assert record.user_id == "user-42"  # type: ignore[attr-defined]
    assert record.cost_usd == 0.0023  # type: ignore[attr-defined]
    assert record.latency_ms is not None  # type: ignore[attr-defined]
