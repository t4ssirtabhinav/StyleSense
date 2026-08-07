"""Tests for backend/services/wardrobe_tagging_service.py (SS-012, amended
A1; SS-029 adds cost-ledger wiring), against fake provider/repository/
storage/cache/rate-limiter/cost-gate/cost-ledger -- no real network/API-key
usage.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from adapters.interfaces import (
    CostLedgerEntry,
    ICostLedger,
    IOccasionRepository,
    IWardrobeRepository,
    OccasionRegistrySnapshot,
)
from ai.ports.interfaces import GarmentTags, IVisionProvider, TokenUsage, VisionTaggingResult
from services.cost_budget_gate import Reservation
from services.cost_config_specs import _DEFAULT_PRICE_TABLE
from services.occasion_normalizer import OccasionNormalizer
from services.price_table import PriceTable
from services.wardrobe_tagging_service import WardrobeTaggingService, original_image_key

_REQUEST_ID = "aaaaaaaa-1111-1111-1111-111111111111"
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


# (SS-025) The 12 seeded registry keys plus the two load-bearing aliases,
# so the tagging service's occasion normalisation is exercised against a
# realistic vocabulary without touching a DB.
class _FakeOccasionRepository(IOccasionRepository):
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self._fail = fail

    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        self.calls += 1
        if self._fail:
            raise RuntimeError("registry read failed")
        return OccasionRegistrySnapshot(
            keys=(
                "office",
                "casual",
                "date_night",
                "wedding_guest",
                "festival",
                "puja",
                "party",
                "travel",
                "workout",
                "beach",
                "formal_event",
                "college",
            ),
            aliases={"wedding": "wedding_guest", "date": "date_night"},
        )


def _valid_tags(**overrides: Any) -> GarmentTags:
    defaults: dict[str, Any] = {
        "category": "ethnic_kurta",
        "subcategory": "straight-fit kurta",
        "color_primary": "#1E3A8A",
        "confidence": 0.9,
        "content_flag": "ok",
        "contains_person": False,
    }
    defaults.update(overrides)
    return GarmentTags(**defaults)


class _FakeProvider(IVisionProvider):
    def __init__(self, results: list[VisionTaggingResult] | None = None) -> None:
        self.calls = 0
        self._results = results
        self.received_image_bytes: list[bytes] = []

    async def tag_garment(self, image_bytes: bytes) -> VisionTaggingResult:
        self.calls += 1
        self.received_image_bytes.append(image_bytes)
        if self._results:
            return self._results.pop(0)
        return VisionTaggingResult(
            success=True, tags=_valid_tags(), latency_ms=50, model="gemini-3.5-flash-lite"
        )


class _FakeRepository(IWardrobeRepository):
    def __init__(self, initial_ai_tags: dict[str, Any] | None = None) -> None:
        self.updates: list[dict[str, Any]] = []
        self.ai_tags: dict[str, Any] = dict(initial_ai_tags or {})

    async def upsert_uploaded_row(
        self, *, jwt: str, item_id: str, user_id: str, image_key: str
    ) -> None:
        pass

    async def update_bg_removal_result(self, **kwargs: Any) -> None:
        pass

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        return "free"

    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        return True

    async def update_tagging_result(
        self,
        *,
        jwt: str,
        item_id: str,
        tag_columns: dict[str, Any] | None,
        tagging_tags: dict[str, Any],
    ) -> None:
        self.ai_tags = {**self.ai_tags, "tagging": tagging_tags}
        self.updates.append(
            {
                "jwt": jwt,
                "item_id": item_id,
                "tag_columns": tag_columns,
                "tagging_tags": tagging_tags,
            }
        )

    # SS-013 mechanical addition: same ABC-extension trap noted in SS-012's
    # own comment above (item_exists/update_tagging_result).
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
    def __init__(self, data: bytes = b"fake-original-bytes", fail: bool = False) -> None:
        self._data = data
        self._fail = fail

    def get_object_bytes(self, key: str) -> bytes:
        if self._fail:
            raise RuntimeError("R2 read failed")
        return self._data

    def put_object_bytes(self, key: str, data: bytes, content_type: str) -> None:
        pass


class _FakeCache:
    def __init__(
        self, cached: dict[str, Any] | None = None, *, inflight_already_present: bool = False
    ) -> None:
        self._cached = cached
        self._inflight_already_present = inflight_already_present
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, dict[str, Any]]] = []
        self.mark_calls: list[str] = []
        self.clear_calls: list[str] = []

    async def get(self, image_hash: str) -> dict[str, Any] | None:
        self.get_calls.append(image_hash)
        return self._cached

    async def set(self, image_hash: str, payload: dict[str, Any]) -> None:
        self.set_calls.append((image_hash, payload))

    async def mark_inflight(self, image_hash: str) -> bool:
        self.mark_calls.append(image_hash)
        return not self._inflight_already_present

    async def clear_inflight(self, image_hash: str) -> None:
        self.clear_calls.append(image_hash)


class _FakeRateLimiter:
    def __init__(self) -> None:
        self.acquire_calls = 0

    async def acquire(self) -> None:
        self.acquire_calls += 1


class _FakeCostBudgetGate:
    def __init__(self) -> None:
        self.reconcile_calls: list[dict[str, Any]] = []

    async def reconcile(self, *, reservation: Reservation, actual_micropaise: int) -> None:
        self.reconcile_calls.append(
            {"reservation": reservation, "actual_micropaise": actual_micropaise}
        )


class _FakeCostLedger(ICostLedger):
    def __init__(self, *, raise_on_record: bool = False) -> None:
        self.records: list[CostLedgerEntry] = []
        self._raise_on_record = raise_on_record

    async def record(self, entry: CostLedgerEntry) -> None:
        if self._raise_on_record:
            raise RuntimeError("ledger write failed")
        self.records.append(entry)

    async def breakdown(self, *, user_id: str, since: Any, until: Any) -> list[dict[str, Any]]:
        return []


def _service(
    *,
    provider: _FakeProvider,
    repository: _FakeRepository,
    storage: _FakeStorage | None = None,
    cache: _FakeCache | None = None,
    rate_limiter: _FakeRateLimiter | None = None,
    occasion_repository: _FakeOccasionRepository | None = None,
    cost_budget_gate: _FakeCostBudgetGate | None = None,
    cost_ledger: _FakeCostLedger | None = None,
) -> tuple[
    WardrobeTaggingService, _FakeStorage, _FakeCache, _FakeRateLimiter, _FakeCostBudgetGate, _FakeCostLedger
]:
    storage = storage or _FakeStorage()
    cache = cache or _FakeCache()
    rate_limiter = rate_limiter or _FakeRateLimiter()
    normalizer = OccasionNormalizer(occasion_repository or _FakeOccasionRepository())
    cost_budget_gate = cost_budget_gate or _FakeCostBudgetGate()
    cost_ledger = cost_ledger or _FakeCostLedger()
    service = WardrobeTaggingService(
        provider,
        repository,
        storage,  # type: ignore[arg-type]
        cache,  # type: ignore[arg-type]
        rate_limiter,  # type: ignore[arg-type]
        normalizer,
        cost_budget_gate,  # type: ignore[arg-type]
        cost_ledger,
    )
    return service, storage, cache, rate_limiter, cost_budget_gate, cost_ledger


async def _tag(
    service: WardrobeTaggingService,
    *,
    jwt: str = "jwt",
    user_id: str = "user-1",
    item_id: str = "item-1",
    reservation: Reservation | None = None,
) -> None:
    await service.tag(
        jwt=jwt,
        user_id=user_id,
        item_id=item_id,
        request_id=_REQUEST_ID,
        reservation=reservation or _reservation(),
        price_table=_PRICE_TABLE,
    )


async def test_cache_hit_skips_provider_and_writes_cached_tags() -> None:
    cached_payload = _valid_tags().model_dump(mode="json")
    provider = _FakeProvider()
    repository = _FakeRepository()
    cache = _FakeCache(cached=cached_payload)
    service, _, cache, *_ = _service(provider=provider, repository=repository, cache=cache)

    await _tag(service)

    assert provider.calls == 0
    assert len(repository.updates) == 1
    assert repository.updates[0]["tagging_tags"]["source"] == "cache"
    assert repository.updates[0]["tag_columns"]["category"] == "ethnic_kurta"


async def test_cache_miss_calls_provider_marks_and_clears_inflight_and_caches_result() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    service, _, cache, rate_limiter, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    assert provider.calls == 1
    assert rate_limiter.acquire_calls == 1
    assert len(cache.mark_calls) == 1
    assert len(cache.clear_calls) == 1
    assert cache.mark_calls == cache.clear_calls  # same image hash
    assert len(cache.set_calls) == 1
    assert len(repository.updates) == 1
    assert repository.updates[0]["tagging_tags"]["source"] == "gemini"


async def test_low_confidence_flags_for_review() -> None:
    provider = _FakeProvider(
        results=[VisionTaggingResult(success=True, tags=_valid_tags(confidence=0.4), latency_ms=10)]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    tagging_tags = repository.updates[0]["tagging_tags"]
    assert tagging_tags["flagged_for_review"] is True
    assert tagging_tags["status"] == "flagged"


async def test_non_clothing_writes_null_category_and_flags_no_crash() -> None:
    provider = _FakeProvider(
        results=[
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(category=None, confidence=0.0, content_flag="not_clothing"),
                latency_ms=10,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    update = repository.updates[0]
    assert update["tag_columns"]["category"] is None
    assert update["tagging_tags"]["status"] == "flagged"


async def test_nsfw_content_flag_nulls_category_and_flags() -> None:
    provider = _FakeProvider(
        results=[
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(content_flag="nsfw"),
                latency_ms=10,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    update = repository.updates[0]
    assert update["tag_columns"]["category"] is None
    assert update["tagging_tags"]["status"] == "flagged"
    assert update["tagging_tags"]["moderation"]["content_flag"] == "nsfw"


async def test_contains_person_keeps_valid_category_but_flags() -> None:
    provider = _FakeProvider(
        results=[
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(contains_person=True),
                latency_ms=10,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    update = repository.updates[0]
    assert update["tag_columns"]["category"] == "ethnic_kurta"
    assert update["tagging_tags"]["status"] == "flagged"
    assert update["tagging_tags"]["moderation"]["contains_person"] is True


async def test_provider_failure_marks_failed_writes_no_columns_clears_inflight_no_raise() -> None:
    provider = _FakeProvider(results=[VisionTaggingResult(success=False, error="timeout")])
    repository = _FakeRepository()
    service, _, cache, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    assert len(repository.updates) == 1
    assert repository.updates[0]["tag_columns"] is None
    assert repository.updates[0]["tagging_tags"]["status"] == "failed"
    assert len(cache.clear_calls) == 1


async def test_ai_tags_non_clobber_preserves_bg_removal_key() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository(initial_ai_tags={"bg_removal": {"source": "replicate"}})
    service, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    assert repository.ai_tags["bg_removal"] == {"source": "replicate"}
    assert "tagging" in repository.ai_tags


async def test_inflight_marker_already_present_short_circuits_without_calling_provider() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    cache = _FakeCache(inflight_already_present=True)
    service, *_ = _service(provider=provider, repository=repository, cache=cache)

    await _tag(service)

    assert provider.calls == 0
    assert len(repository.updates) == 0


async def test_r2_read_failure_marks_failed_no_raise() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(fail=True)
    service, *_ = _service(provider=provider, repository=repository, storage=storage)

    await _tag(service)

    assert repository.updates[0]["tag_columns"] is None
    assert repository.updates[0]["tagging_tags"]["status"] == "failed"


async def test_successful_call_logs_ai_call_with_user_id_latency_and_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    with caplog.at_level(logging.INFO):
        await _tag(service, user_id="user-42")

    ai_call_records = [r for r in caplog.records if r.message == "ai_call"]
    assert len(ai_call_records) == 1
    record = ai_call_records[0]
    assert record.user_id == "user-42"  # type: ignore[attr-defined]
    assert record.latency_ms is not None  # type: ignore[attr-defined]
    assert record.model == "gemini-3.5-flash-lite"  # type: ignore[attr-defined]


def test_original_image_key_shape() -> None:
    assert original_image_key("user-1", "item-1") == "wardrobe/user-1/item-1/original.jpg"


# --- SS-025: occasion normalisation at write boundary #1 -------------------


async def test_write_success_writes_normalised_and_deduped_occasion_tags() -> None:
    provider = _FakeProvider(
        [
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(
                    occasion_tags=["  Wedding Guest ", "wedding", "Festival", "festival"]
                ),
                latency_ms=50,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    await _tag(service)

    written = repository.updates[0]["tag_columns"]["occasion_tags"]
    # 'wedding' aliases onto wedding_guest, so it dedupes away; first-
    # occurrence order is preserved and nothing is sorted.
    assert written == ["wedding_guest", "festival"]


async def test_unknown_occasion_is_still_written_and_logged_exactly_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider(
        [
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(occasion_tags=["festival", "Ganesh Chaturthi"]),
                latency_ms=50,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    with caplog.at_level(logging.WARNING):
        await _tag(service)

    # Never dropped -- the tag reaches the column.
    assert repository.updates[0]["tag_columns"]["occasion_tags"] == [
        "festival",
        "ganesh_chaturthi",
    ]

    records = [r for r in caplog.records if r.message == "occasion_unknown"]
    assert len(records) == 1
    assert records[0].user_id == "user-1"  # type: ignore[attr-defined]
    assert records[0].item_id == "item-1"  # type: ignore[attr-defined]
    assert records[0].slug == "ganesh_chaturthi"  # type: ignore[attr-defined]


async def test_no_unknown_log_when_every_occasion_is_canonical(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider(
        [
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(occasion_tags=["festival", "puja"]),
                latency_ms=50,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    with caplog.at_level(logging.WARNING):
        await _tag(service)

    assert [r for r in caplog.records if r.message == "occasion_unknown"] == []


async def test_registry_read_failure_does_not_fail_the_item_write() -> None:
    """Tagging must never fail merely because the occasion registry read
    failed -- normalisation degrades to shape-only and the DB trigger
    completes the alias mapping."""
    provider = _FakeProvider(
        [
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(occasion_tags=["  Wedding Guest "]),
                latency_ms=50,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ = _service(
        provider=provider,
        repository=repository,
        occasion_repository=_FakeOccasionRepository(fail=True),
    )

    await _tag(service)

    assert len(repository.updates) == 1
    assert repository.updates[0]["tag_columns"]["occasion_tags"] == ["wedding_guest"]
    assert repository.updates[0]["tagging_tags"]["status"] == "tagged"


# --- SS-029: cost-ledger wiring ---------------------------------------------


async def test_cache_hit_records_ledger_row_with_zero_cost_and_refunds_reservation() -> None:
    cached_payload = _valid_tags().model_dump(mode="json")
    provider = _FakeProvider()
    repository = _FakeRepository()
    cache = _FakeCache(cached=cached_payload)
    reservation = _reservation(reserved_micropaise=5_000_000)
    service, _, _, _, gate, ledger = _service(
        provider=provider, repository=repository, cache=cache
    )

    await _tag(service, reservation=reservation)

    assert provider.calls == 0
    assert len(gate.reconcile_calls) == 1
    assert gate.reconcile_calls[0]["reservation"] is reservation
    assert gate.reconcile_calls[0]["actual_micropaise"] == 0
    assert len(ledger.records) == 1
    row = ledger.records[0]
    assert row.cache_hit is True
    assert row.cost_micropaise == 0
    assert row.outcome == "success"
    assert row.request_id == _REQUEST_ID


async def test_inflight_dedupe_refunds_and_records_no_row() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    cache = _FakeCache(inflight_already_present=True)
    reservation = _reservation(reserved_micropaise=3_000_000)
    service, *_ , gate, ledger = _service(provider=provider, repository=repository, cache=cache)

    await _tag(service, reservation=reservation)

    assert provider.calls == 0
    assert len(gate.reconcile_calls) == 1
    assert gate.reconcile_calls[0]["actual_micropaise"] == 0
    assert ledger.records == []


async def test_provider_failure_records_failed_outcome_row_without_refund() -> None:
    provider = _FakeProvider(results=[VisionTaggingResult(success=False, error="timeout")])
    repository = _FakeRepository()
    reservation = _reservation(reserved_micropaise=2_000_000)
    service, *_ , gate, ledger = _service(provider=provider, repository=repository)

    await _tag(service, reservation=reservation)

    assert len(gate.reconcile_calls) == 1
    # Not refunded to zero -- reconciled to whatever the (estimated) actual
    # cost resolves to, per design edge case 15.
    assert len(ledger.records) == 1
    assert ledger.records[0].outcome == "failed"


async def test_storage_read_failure_refunds_and_records_no_row() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(fail=True)
    reservation = _reservation(reserved_micropaise=1_500_000)
    service, *_ , gate, ledger = _service(
        provider=provider, repository=repository, storage=storage
    )

    await _tag(service, reservation=reservation)

    assert len(gate.reconcile_calls) == 1
    assert gate.reconcile_calls[0]["actual_micropaise"] == 0
    assert ledger.records == []


async def test_successful_tag_reconciles_and_records_a_priced_or_estimated_row() -> None:
    provider = _FakeProvider(
        results=[
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(),
                latency_ms=42,
                model="gemini-3.5-flash-lite",
                usage=TokenUsage(tokens_in=1200, tokens_out=250),
            )
        ]
    )
    repository = _FakeRepository()
    reservation = _reservation(reserved_micropaise=2_000_000)
    service, *_ , gate, ledger = _service(provider=provider, repository=repository)

    await _tag(service, reservation=reservation)

    assert len(gate.reconcile_calls) == 1
    assert len(ledger.records) == 1
    row = ledger.records[0]
    assert row.outcome == "success"
    assert row.tokens_in == 1200
    assert row.tokens_out == 250
    assert row.cost_micropaise > 0
    assert row.request_id == _REQUEST_ID


async def test_no_usage_falls_back_to_default_tokens_and_forces_estimated() -> None:
    provider = _FakeProvider(
        results=[
            VisionTaggingResult(
                success=True,
                tags=_valid_tags(),
                latency_ms=42,
                model="gemini-3.5-flash-lite",
                usage=None,
            )
        ]
    )
    repository = _FakeRepository()
    service, *_ , gate, ledger = _service(provider=provider, repository=repository)

    await _tag(service)

    row = ledger.records[0]
    assert row.tokens_in is None
    assert row.tokens_out is None
    assert row.pricing_status == "estimated"


async def test_ledger_failure_does_not_break_the_tagging_pipeline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Defense in depth on top of ICostLedger.record's own "never raises"
    contract (SupabaseCostLedger already guarantees it): even a misbehaving
    ICostLedger implementation must not break the tagging pipeline whose
    Gemini call already succeeded -- tags are still written."""
    provider = _FakeProvider()
    repository = _FakeRepository()
    ledger = _FakeCostLedger(raise_on_record=True)
    service, *_ = _service(provider=provider, repository=repository, cost_ledger=ledger)

    with caplog.at_level(logging.ERROR):
        await _tag(service)

    assert len(repository.updates) == 1
    assert repository.updates[0]["tagging_tags"]["source"] == "gemini"
    assert ledger.records == []
    assert any(r.message == "ledger_write_failed" for r in caplog.records)
