"""Tests for backend/services/wardrobe_tagging_service.py (SS-012, amended
A1), against fake provider/repository/storage/cache/rate-limiter -- no real
network/API-key usage.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from adapters.interfaces import (
    IOccasionRepository,
    IWardrobeRepository,
    OccasionRegistrySnapshot,
)
from ai.ports.interfaces import GarmentTags, IVisionProvider, VisionTaggingResult
from services.occasion_normalizer import OccasionNormalizer
from services.wardrobe_tagging_service import WardrobeTaggingService, original_image_key


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


def _service(
    *,
    provider: _FakeProvider,
    repository: _FakeRepository,
    storage: _FakeStorage | None = None,
    cache: _FakeCache | None = None,
    rate_limiter: _FakeRateLimiter | None = None,
    occasion_repository: _FakeOccasionRepository | None = None,
) -> tuple[WardrobeTaggingService, _FakeStorage, _FakeCache, _FakeRateLimiter]:
    storage = storage or _FakeStorage()
    cache = cache or _FakeCache()
    rate_limiter = rate_limiter or _FakeRateLimiter()
    normalizer = OccasionNormalizer(occasion_repository or _FakeOccasionRepository())
    service = WardrobeTaggingService(
        provider,
        repository,
        storage,  # type: ignore[arg-type]
        cache,  # type: ignore[arg-type]
        rate_limiter,  # type: ignore[arg-type]
        normalizer,
    )
    return service, storage, cache, rate_limiter


async def test_cache_hit_skips_provider_and_writes_cached_tags() -> None:
    cached_payload = _valid_tags().model_dump(mode="json")
    provider = _FakeProvider()
    repository = _FakeRepository()
    cache = _FakeCache(cached=cached_payload)
    service, _, cache, _ = _service(provider=provider, repository=repository, cache=cache)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    assert provider.calls == 0
    assert len(repository.updates) == 1
    assert repository.updates[0]["tagging_tags"]["source"] == "cache"
    assert repository.updates[0]["tag_columns"]["category"] == "ethnic_kurta"


async def test_cache_miss_calls_provider_marks_and_clears_inflight_and_caches_result() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    service, _, cache, rate_limiter = _service(provider=provider, repository=repository)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    update = repository.updates[0]
    assert update["tag_columns"]["category"] == "ethnic_kurta"
    assert update["tagging_tags"]["status"] == "flagged"
    assert update["tagging_tags"]["moderation"]["contains_person"] is True


async def test_provider_failure_marks_failed_writes_no_columns_clears_inflight_no_raise() -> None:
    provider = _FakeProvider(results=[VisionTaggingResult(success=False, error="timeout")])
    repository = _FakeRepository()
    service, _, cache, _ = _service(provider=provider, repository=repository)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    assert len(repository.updates) == 1
    assert repository.updates[0]["tag_columns"] is None
    assert repository.updates[0]["tagging_tags"]["status"] == "failed"
    assert len(cache.clear_calls) == 1


async def test_ai_tags_non_clobber_preserves_bg_removal_key() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository(initial_ai_tags={"bg_removal": {"source": "replicate"}})
    service, *_ = _service(provider=provider, repository=repository)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    assert repository.ai_tags["bg_removal"] == {"source": "replicate"}
    assert "tagging" in repository.ai_tags


async def test_inflight_marker_already_present_short_circuits_without_calling_provider() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    cache = _FakeCache(inflight_already_present=True)
    service, *_ = _service(provider=provider, repository=repository, cache=cache)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    assert provider.calls == 0
    assert len(repository.updates) == 0


async def test_r2_read_failure_marks_failed_no_raise() -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    storage = _FakeStorage(fail=True)
    service, *_ = _service(provider=provider, repository=repository, storage=storage)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    assert repository.updates[0]["tag_columns"] is None
    assert repository.updates[0]["tagging_tags"]["status"] == "failed"


async def test_successful_call_logs_ai_call_with_user_id_latency_and_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    repository = _FakeRepository()
    service, *_ = _service(provider=provider, repository=repository)

    with caplog.at_level(logging.INFO):
        await service.tag(jwt="jwt", user_id="user-42", item_id="item-1")

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
    service, _, _, _ = _service(provider=provider, repository=repository)

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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
    service, _, _, _ = _service(provider=provider, repository=repository)

    with caplog.at_level(logging.WARNING):
        await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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
    service, _, _, _ = _service(provider=provider, repository=repository)

    with caplog.at_level(logging.WARNING):
        await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

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
    service, _, _, _ = _service(
        provider=provider,
        repository=repository,
        occasion_repository=_FakeOccasionRepository(fail=True),
    )

    await service.tag(jwt="jwt", user_id="user-1", item_id="item-1")

    assert len(repository.updates) == 1
    assert repository.updates[0]["tag_columns"]["occasion_tags"] == ["wedding_guest"]
    assert repository.updates[0]["tagging_tags"]["status"] == "tagged"
