"""Tests for backend/services/wardrobe_bg_removal_service.py (SS-011;
SS-029 adds cost-ledger wiring)."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

import pytest
from PIL import Image

from adapters.interfaces import CostLedgerEntry, ICostLedger, IWardrobeRepository
from ai.ports.interfaces import BackgroundRemovalResult, IBackgroundRemovalProvider
from services.circuit_breaker import CircuitBreaker
from services.cost_budget_gate import Reservation
from services.cost_config_specs import _DEFAULT_PRICE_TABLE
from services.image_processing import resize_for_bg_removal
from services.price_table import PriceTable
from services.wardrobe_bg_removal_service import (
    WardrobeBgRemovalService,
    clean_image_key,
    thumbnail_image_key,
)

_REQUEST_ID = "bbbbbbbb-1111-1111-1111-111111111111"
_PRICE_TABLE = PriceTable(_DEFAULT_PRICE_TABLE)


def _reservation(*, reserved_micropaise: int = 2_000_000, touched_redis: bool = True) -> Reservation:
    return Reservation(
        user_id="user-1",
        tier="free",
        reserved_micropaise=reserved_micropaise,
        daily_key="stylesense:cost:daily:user-1:2026-07-30",
        monthly_key="stylesense:cost:monthly:user-1:2026-07",
        daily_current=reserved_micropaise,
        monthly_current=reserved_micropaise,
        daily_ceiling=500_000_000,
        monthly_ceiling=2_500_000_000,
        touched_redis=touched_redis,
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

    # SS-012 mechanical addition: IWardrobeRepository gained two new
    # abstractmethods (item_exists, update_tagging_result) -- this fake
    # must implement both (no-op stubs) or it fails to instantiate against
    # the extended ABC. Flagged in the SS-012 design doc as a
    # green-locally/red-in-CI trap if skipped.
    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        return True

    async def update_tagging_result(self, **kwargs: Any) -> None:
        pass

    # SS-013 mechanical addition: same ABC-extension trap as above.
    async def get_item_image_info(self, *, jwt: str, item_id: str) -> dict[str, Any] | None:
        return None

    # SS-014 mechanical addition: same ABC-extension trap as above.
    async def get_items_image_info_bulk(
        self, *, jwt: str, item_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        return {}

    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        return True

    # SS-020 mechanical addition: same ABC-extension trap as above.
    async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        return []

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        return None


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


class _FakeCostBudgetGate:
    def __init__(self) -> None:
        self.reconcile_calls: list[dict[str, Any]] = []

    async def reconcile(self, *, reservation: Reservation, actual_micropaise: int) -> None:
        self.reconcile_calls.append(
            {"reservation": reservation, "actual_micropaise": actual_micropaise}
        )


class _FakeCostLedger(ICostLedger):
    def __init__(self) -> None:
        self.records: list[CostLedgerEntry] = []

    async def record(self, entry: CostLedgerEntry) -> None:
        self.records.append(entry)

    async def breakdown(self, *, user_id: str, since: Any, until: Any) -> list[dict[str, Any]]:
        return []


def _build_service(
    provider: Any,
    repository: Any,
    storage: Any,
    circuit_breaker: Any,
    *,
    cost_budget_gate: _FakeCostBudgetGate | None = None,
    cost_ledger: _FakeCostLedger | None = None,
    max_concurrent_replicate_calls: int = 3,
) -> tuple[WardrobeBgRemovalService, _FakeCostBudgetGate, _FakeCostLedger]:
    cost_budget_gate = cost_budget_gate or _FakeCostBudgetGate()
    cost_ledger = cost_ledger or _FakeCostLedger()
    service = WardrobeBgRemovalService(
        provider,
        repository,
        storage,
        circuit_breaker,
        cost_budget_gate,  # type: ignore[arg-type]
        cost_ledger,
        max_concurrent_replicate_calls=max_concurrent_replicate_calls,
    )
    return service, cost_budget_gate, cost_ledger


async def _process(
    service: WardrobeBgRemovalService,
    *,
    jwt: str = "jwt",
    user_id: str = "user-1",
    item_id: str = "item-1",
    reservation: Reservation | None = None,
) -> None:
    await service.process(
        jwt=jwt,
        user_id=user_id,
        item_id=item_id,
        request_id=_REQUEST_ID,
        reservation=reservation or _reservation(),
        price_table=_PRICE_TABLE,
    )


async def test_happy_path_uploads_clean_and_thumbnail_and_marks_bg_removed() -> None:
    # Original wider than the 800px proxy default, so we can distinguish
    # "provider received the full-resolution original" (wrong, post-QA
    # amendment) from "provider received the downscaled proxy" (right).
    original_bytes = _jpeg_bytes(size=(1200, 800))
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(original_bytes)
    circuit_breaker = _FakeCircuitBreaker()

    service, gate, ledger = _build_service(provider, repository, storage, circuit_breaker)
    await _process(service)

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
    clean_bytes = next(
        data for key, data, _ in storage.puts if key == clean_image_key("user-1", "item-1")
    )
    with Image.open(io.BytesIO(clean_bytes)) as clean_image:
        assert clean_image.mode == "RGBA"
        assert clean_image.size == (1200, 800)

    assert len(repository.updates) == 1
    update = repository.updates[0]
    assert update["processing_status"] == "bg_removed"
    assert update["image_clean_url"] == clean_image_key("user-1", "item-1")
    assert update["thumbnail_url"] == thumbnail_image_key("user-1", "item-1")
    assert update["bg_removal_tags"]["source"] == "replicate"

    assert len(ledger.records) == 1
    assert ledger.records[0].outcome == "success"
    assert ledger.records[0].provider == "replicate"
    assert ledger.records[0].model == "bria-rmbg"
    assert len(gate.reconcile_calls) == 1


async def test_already_transparent_input_skips_provider_call_and_still_marks_bg_removed() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_white_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service, gate, ledger = _build_service(provider, repository, storage, circuit_breaker)
    reservation = _reservation(reserved_micropaise=1_000_000)
    await _process(service, reservation=reservation)

    assert provider.calls == 0
    assert len(repository.updates) == 1
    update = repository.updates[0]
    assert update["processing_status"] == "bg_removed"
    assert update["bg_removal_tags"]["source"] == "skipped_already_transparent"
    # Never calls Replicate -- full refund, no ledger row (design edge case 13).
    assert len(gate.reconcile_calls) == 1
    assert gate.reconcile_calls[0]["actual_micropaise"] == 0
    assert ledger.records == []


async def test_circuit_open_skips_provider_marks_bg_pending_no_cost() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker(open_=True)

    service, gate, ledger = _build_service(provider, repository, storage, circuit_breaker)
    await _process(service)

    assert provider.calls == 0
    assert len(repository.updates) == 1
    update = repository.updates[0]
    assert update["processing_status"] == "bg_pending"
    assert update["bg_removal_tags"]["source"] == "circuit_open"
    assert len(gate.reconcile_calls) == 1
    assert gate.reconcile_calls[0]["actual_micropaise"] == 0
    assert ledger.records == []


async def test_storage_read_failure_refunds_and_records_no_row() -> None:
    class _FailingStorage:
        def get_object_bytes(self, key: str) -> bytes:
            raise RuntimeError("R2 read failed")

        def put_object_bytes(self, key: str, data: bytes, content_type: str) -> None:
            pass

    provider = _FakeProvider()
    repository = _FakeRepository()
    circuit_breaker = _FakeCircuitBreaker()

    service, gate, ledger = _build_service(provider, repository, _FailingStorage(), circuit_breaker)
    await _process(service)

    assert repository.updates[0]["bg_removal_tags"]["source"] == "r2_read_failed"
    assert len(gate.reconcile_calls) == 1
    assert gate.reconcile_calls[0]["actual_micropaise"] == 0
    assert ledger.records == []


async def test_provider_failure_not_yet_third_marks_bg_pending_records_one_failure() -> None:
    provider = _FakeProvider(results=[BackgroundRemovalResult(success=False, error="boom")])
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service, gate, ledger = _build_service(provider, repository, storage, circuit_breaker)
    await _process(service)

    assert circuit_breaker.failures_recorded == 1
    assert repository.updates[0]["processing_status"] == "bg_pending"
    # A billed-but-failed provider call -- NOT refunded (design edge case 15).
    assert len(gate.reconcile_calls) == 1
    assert len(ledger.records) == 1
    assert ledger.records[0].outcome == "failed"


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
        service, *_ = _build_service(provider, repository, storage, real_circuit_breaker)
        await _process(service)

    assert await real_circuit_breaker.is_open() is True


async def test_r2_upload_failure_after_successful_provider_call_marks_bg_pending_and_still_bills(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes(), fail_put=True)
    circuit_breaker = _FakeCircuitBreaker()

    service, gate, ledger = _build_service(provider, repository, storage, circuit_breaker)

    with caplog.at_level(logging.INFO):
        await _process(service)

    assert repository.updates[0]["processing_status"] == "bg_pending"
    ai_call_records = [r for r in caplog.records if r.message == "ai_call"]
    assert len(ai_call_records) == 1
    # The Replicate call itself succeeded (and was billed) before the R2
    # write failed -- the ledger row/reconcile already happened.
    assert len(ledger.records) == 1
    assert ledger.records[0].outcome == "success"
    assert len(gate.reconcile_calls) == 1


async def test_semaphore_caps_concurrency_at_three_for_ten_parallel_calls() -> None:
    provider = _FakeProvider(delay=0.05)
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service, *_ = _build_service(
        provider, repository, storage, circuit_breaker, max_concurrent_replicate_calls=3
    )

    await asyncio.gather(
        *(_process(service, item_id=f"item-{i}") for i in range(10))
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

    service, *_ = _build_service(provider, repository, storage, circuit_breaker)

    with caplog.at_level(logging.INFO):
        await _process(service, user_id="user-42")

    ai_call_records = [r for r in caplog.records if r.message == "ai_call"]
    assert len(ai_call_records) == 1
    record = ai_call_records[0]
    assert record.user_id == "user-42"  # type: ignore[attr-defined]
    assert record.cost_micropaise is not None  # type: ignore[attr-defined]
    assert record.latency_ms is not None  # type: ignore[attr-defined]


async def test_ledger_failure_does_not_break_the_bg_removal_pipeline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _RaisingLedger(ICostLedger):
        async def record(self, entry: CostLedgerEntry) -> None:
            raise RuntimeError("ledger write failed")

        async def breakdown(self, *, user_id: str, since: Any, until: Any) -> list[dict[str, Any]]:
            return []

    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(_jpeg_bytes())
    circuit_breaker = _FakeCircuitBreaker()

    service = WardrobeBgRemovalService(
        provider,
        repository,
        storage,  # type: ignore[arg-type]
        circuit_breaker,  # type: ignore[arg-type]
        _FakeCostBudgetGate(),  # type: ignore[arg-type]
        _RaisingLedger(),
    )

    with caplog.at_level(logging.ERROR):
        await _process(service)

    assert repository.updates[0]["processing_status"] == "bg_removed"
    assert any(r.message == "ledger_write_failed" for r in caplog.records)
