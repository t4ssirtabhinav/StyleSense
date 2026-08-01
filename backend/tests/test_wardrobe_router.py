"""Tests for backend/routers/wardrobe.py (SS-011), FastAPI TestClient.

Background-task timing note: this repo's installed fastapi/starlette
executes ``BackgroundTasks`` synchronously within the TestClient's request
call (verified directly for SS-006, see test_outfit_suggestions_router.py
and docs/worklog/SS-006.md) -- so a background task's side effects are
observable immediately after the request call returns here too, no
polling/synchronization primitive needed.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from adapters.interfaces import CostLedgerEntry, ICostLedger, IWardrobeRepository
from ai.ports.interfaces import (
    BackgroundRemovalResult,
    GarmentTags,
    IBackgroundRemovalProvider,
    IVisionProvider,
    VisionTaggingResult,
)
from dependencies.auth import get_current_user_id
from main import app
from routers.wardrobe import (
    get_app_config_snapshot,
    get_background_removal_provider,
    get_circuit_breaker,
    get_cost_budget_gate,
    get_cost_ledger,
    get_daily_rate_limiter,
    get_deletion_service,
    get_r2_storage_client,
    get_tag_cache,
    get_vision_provider,
    get_wardrobe_repository,
)
from services.app_config import AppConfigSnapshot
from services.cost_budget_gate import GateDecision, Reservation
from services.wardrobe_deletion_service import WardrobeDeletionService

client = TestClient(app)

VALID_ITEM_ID = "11111111-1111-1111-1111-111111111111"


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (100, 100), (20, 40, 60))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeRepository(IWardrobeRepository):
    def __init__(
        self,
        plan_tier: str = "free",
        *,
        exists: bool = True,
        image_info: dict[str, Any] | None = None,
        bulk_image_info: dict[str, dict[str, Any]] | None = None,
        delete_returns: bool = True,
    ) -> None:
        self.plan_tier = plan_tier
        self.exists = exists
        self.image_info = image_info
        self.bulk_image_info = bulk_image_info
        self.delete_returns = delete_returns
        self.upserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.tagging_updates: list[dict[str, Any]] = []
        self.deleted_item_ids: list[str] = []

    async def upsert_uploaded_row(
        self, *, jwt: str, item_id: str, user_id: str, image_key: str
    ) -> None:
        self.upserts.append({"item_id": item_id, "user_id": user_id, "image_key": image_key})

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
        self.updates.append({"item_id": item_id, "processing_status": processing_status})

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        return self.plan_tier

    # SS-012 mechanical addition: IWardrobeRepository gained two new
    # abstractmethods -- this fake must implement both or it fails to
    # instantiate against the extended ABC.
    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        return self.exists

    async def update_tagging_result(
        self,
        *,
        jwt: str,
        item_id: str,
        tag_columns: dict[str, Any] | None,
        tagging_tags: dict[str, Any],
    ) -> None:
        self.tagging_updates.append(
            {"item_id": item_id, "tag_columns": tag_columns, "tagging_tags": tagging_tags}
        )

    # SS-013
    async def get_item_image_info(self, *, jwt: str, item_id: str) -> dict[str, Any] | None:
        return self.image_info

    # SS-014
    async def get_items_image_info_bulk(
        self, *, jwt: str, item_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        return self.bulk_image_info or {}

    # SS-015
    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        if self.delete_returns:
            self.deleted_item_ids.append(item_id)
        return self.delete_returns


class _FakeRateLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed
        self.calls: list[dict[str, Any]] = []

    async def check_and_increment(self, user_id: str, *, skip: bool = False) -> bool:
        self.calls.append({"user_id": user_id, "skip": skip})
        if skip:
            return True
        return self._allowed


class _FakeProvider(IBackgroundRemovalProvider):
    async def remove_background(self, image_bytes: bytes) -> BackgroundRemovalResult:
        return BackgroundRemovalResult(success=True, image_bytes=_png_bytes(), latency_ms=10)


def _png_bytes() -> bytes:
    image = Image.new("RGBA", (100, 100), (10, 20, 30, 255))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class _FakeStorage:
    def get_object_bytes(self, key: str) -> bytes:
        return _jpeg_bytes()

    def put_object_bytes(self, key: str, data: bytes, content_type: str) -> None:
        pass

    def generate_presigned_get_url(self, key: str, expiry_seconds: int) -> str:
        return f"https://fake-r2.example.com/{key}?expires={expiry_seconds}"


class _FakeVisionProvider(IVisionProvider):
    def __init__(self) -> None:
        self.call_count = 0

    async def tag_garment(self, image_bytes: bytes) -> VisionTaggingResult:
        self.call_count += 1
        return VisionTaggingResult(
            success=True,
            tags=GarmentTags(
                category="ethnic_kurta",
                confidence=0.9,
                content_flag="ok",
                contains_person=False,
            ),
            latency_ms=10,
            source="gemini",
        )


class _FakeCircuitBreaker:
    async def is_open(self) -> bool:
        return False

    async def record_success(self) -> None:
        pass

    async def record_failure(self) -> None:
        pass


class _FakeCostBudgetGate:
    """(SS-029) Router-level fake -- always allows unless constructed with
    ``allowed=False``, mirroring _FakeRateLimiter's own shape above. Real
    CostBudgetGate/UpstashRateLimiter correctness is exercised in
    test_cost_budget_gate.py / test_cost_budget_gate_concurrency.py, not
    here -- these tests only need to prove the ROUTER wires the gate
    correctly (dispatch-on-allow, 429-on-deny, no dispatch on deny)."""

    def __init__(self, *, allowed: bool = True, scope: str | None = None) -> None:
        self._allowed = allowed
        self._scope = scope
        self.reserve_calls: list[dict[str, Any]] = []
        self.reconcile_calls: list[dict[str, Any]] = []

    async def reconcile(self, *, reservation: Reservation, actual_micropaise: int) -> None:
        self.reconcile_calls.append(
            {"reservation": reservation, "actual_micropaise": actual_micropaise}
        )

    async def reserve(
        self,
        *,
        user_id: str,
        tier: str | None,
        estimate_micropaise: int,
        config_snapshot: AppConfigSnapshot,
    ) -> GateDecision:
        self.reserve_calls.append(
            {"user_id": user_id, "tier": tier, "estimate_micropaise": estimate_micropaise}
        )
        if not self._allowed:
            return GateDecision(allowed=False, scope=self._scope or "daily", degraded=False, reservation=None)
        return GateDecision(
            allowed=True,
            scope=None,
            degraded=False,
            reservation=Reservation(
                user_id=user_id,
                tier=tier or "free",
                reserved_micropaise=estimate_micropaise,
                daily_key="stylesense:cost:daily:test",
                monthly_key="stylesense:cost:monthly:test",
                daily_current=estimate_micropaise,
                monthly_current=estimate_micropaise,
                daily_ceiling=999_999_999_999,
                monthly_ceiling=999_999_999_999,
                touched_redis=True,
            ),
        )


class _FakeCostLedgerForRouter(ICostLedger):
    def __init__(self) -> None:
        self.records: list[CostLedgerEntry] = []

    async def record(self, entry: CostLedgerEntry) -> None:
        self.records.append(entry)

    async def breakdown(self, *, user_id: str, since: Any, until: Any) -> list[dict[str, Any]]:
        return []


def teardown_function() -> None:
    app.dependency_overrides.clear()


def _override_infra(
    repository: _FakeRepository,
    rate_limiter: _FakeRateLimiter,
    *,
    cost_budget_gate: _FakeCostBudgetGate | None = None,
) -> None:
    app.dependency_overrides[get_wardrobe_repository] = lambda: repository
    app.dependency_overrides[get_daily_rate_limiter] = lambda: rate_limiter
    app.dependency_overrides[get_background_removal_provider] = lambda: _FakeProvider()
    app.dependency_overrides[get_r2_storage_client] = lambda: _FakeStorage()
    app.dependency_overrides[get_circuit_breaker] = lambda: _FakeCircuitBreaker()
    app.dependency_overrides[get_cost_budget_gate] = lambda: (cost_budget_gate or _FakeCostBudgetGate())
    app.dependency_overrides[get_cost_ledger] = lambda: _FakeCostLedgerForRouter()
    app.dependency_overrides[get_app_config_snapshot] = lambda: AppConfigSnapshot()


def test_missing_or_invalid_auth_returns_401_via_real_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    with patch("dependencies.auth.create_client") as mock_create_client:
        mock_create_client.return_value.auth.get_user.side_effect = RuntimeError("invalid")

        response = client.post(
            "/wardrobe/remove-bg",
            headers={"Authorization": "Bearer some-invalid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 401


def test_missing_authorization_header_returns_401() -> None:
    response = client.post("/wardrobe/remove-bg", json={"item_id": VALID_ITEM_ID})

    assert response.status_code == 401


def test_free_user_under_daily_cap_returns_202_and_creates_row_before_response() -> None:
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=True)
    _override_infra(repository, rate_limiter)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.post(
        "/wardrobe/remove-bg",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 202
    body = response.json()
    assert body == {"status": "processing", "item_id": VALID_ITEM_ID}
    assert len(repository.upserts) == 1
    assert repository.upserts[0]["item_id"] == VALID_ITEM_ID
    assert repository.upserts[0]["user_id"] == "user-1"


def test_free_user_at_daily_cap_returns_429_no_row_created_no_task_queued() -> None:
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=False)
    _override_infra(repository, rate_limiter)
    app.dependency_overrides[get_current_user_id] = lambda: "user-2"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(
            "/wardrobe/remove-bg",
            headers={"Authorization": "Bearer valid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 429
    assert len(repository.upserts) == 0
    mock_add_task.assert_not_called()


def test_premium_user_beyond_20_calls_still_returns_202_rate_limiter_skipped() -> None:
    repository = _FakeRepository(plan_tier="premium")
    rate_limiter = _FakeRateLimiter(allowed=False)  # would deny if not skipped
    _override_infra(repository, rate_limiter)
    app.dependency_overrides[get_current_user_id] = lambda: "user-premium"

    response = client.post(
        "/wardrobe/remove-bg",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 202
    assert rate_limiter.calls[0]["skip"] is True


def test_dependency_override_swaps_the_background_removal_provider() -> None:
    """Mirrors SS-006's router-swappability test pattern
    (test_outfit_suggestions_router.py::test_dependency_override_swaps_the_styling_provider).
    Design doc names the override target as `IBackgroundRemovalProvider`;
    dependency_overrides must key on the exact callable passed to Depends()
    (`get_background_removal_provider`), matching the actual established
    SS-006 pattern (which overrides `get_styling_provider`, not the port
    ABC directly) -- flagged here since this is what's actually exercised.
    """
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=True)
    _override_infra(repository, rate_limiter)
    app.dependency_overrides[get_current_user_id] = lambda: "user-3"

    class _CountingFakeProvider(IBackgroundRemovalProvider):
        def __init__(self) -> None:
            self.call_count = 0

        async def remove_background(self, image_bytes: bytes) -> BackgroundRemovalResult:
            self.call_count += 1
            return BackgroundRemovalResult(success=True, image_bytes=_png_bytes(), latency_ms=5)

    counting_provider = _CountingFakeProvider()
    app.dependency_overrides[get_background_removal_provider] = lambda: counting_provider

    response = client.post(
        "/wardrobe/remove-bg",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 202
    assert counting_provider.call_count == 1


def test_malformed_item_id_returns_422_not_500() -> None:
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=True)
    _override_infra(repository, rate_limiter)
    app.dependency_overrides[get_current_user_id] = lambda: "user-4"

    response = client.post(
        "/wardrobe/remove-bg",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": "not-a-uuid"},
    )

    assert response.status_code == 422


# --- SS-029: cost budget gate on POST /wardrobe/remove-bg -------------------


def test_remove_bg_budget_denied_returns_429_no_row_created_no_task_queued() -> None:
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=True)  # the OLD call-count limiter allows
    gate = _FakeCostBudgetGate(allowed=False, scope="daily")
    _override_infra(repository, rate_limiter, cost_budget_gate=gate)
    app.dependency_overrides[get_current_user_id] = lambda: "user-budget-1"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(
            "/wardrobe/remove-bg",
            headers={"Authorization": "Bearer valid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 429
    assert len(repository.upserts) == 0
    mock_add_task.assert_not_called()
    assert gate.reserve_calls[0]["user_id"] == "user-budget-1"


def test_remove_bg_budget_gate_runs_before_dispatch() -> None:
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=True)
    gate = _FakeCostBudgetGate(allowed=True)
    _override_infra(repository, rate_limiter, cost_budget_gate=gate)
    app.dependency_overrides[get_current_user_id] = lambda: "user-budget-2"

    response = client.post(
        "/wardrobe/remove-bg",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 202
    assert len(gate.reserve_calls) == 1
    assert len(gate.reconcile_calls) == 1  # dispatched task ran synchronously (TestClient)


# --- SS-012: POST /wardrobe/tag -------------------------------------------


class _FakeTagCache:
    """In-memory stand-in for the real Upstash-backed TagCache.

    (SS-025) Added because the real TagCache was NOT overridden here, so
    these tests talked to the live Upstash instance and SELF-POISONED: the
    first run's `_write_success` wrote `tag:{md5}` with a 30-DAY TTL, and
    every subsequent run within those 30 days took the cache-hit branch,
    skipping the provider entirely -- making
    `test_tag_dependency_override_swaps_the_vision_provider` fail with
    `call_count == 0`. Confirmed by reading the live key's TTL (2,500,187s
    remaining, i.e. written ~1 day before this ticket's Developer phase, so
    the failure predates SS-025). Faking it here matches what every other
    dependency in this helper already does. Logged as BL-091.
    """

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}
        self.inflight: set[str] = set()

    async def get(self, image_hash: str) -> dict[str, Any] | None:
        return self.entries.get(image_hash)

    async def set(self, image_hash: str, payload: dict[str, Any]) -> None:
        self.entries[image_hash] = payload

    async def mark_inflight(self, image_hash: str) -> bool:
        if image_hash in self.inflight:
            return False
        self.inflight.add(image_hash)
        return True

    async def clear_inflight(self, image_hash: str) -> None:
        self.inflight.discard(image_hash)


def _override_tag_infra(
    repository: _FakeRepository,
    provider: _FakeVisionProvider,
    *,
    cost_budget_gate: _FakeCostBudgetGate | None = None,
) -> None:
    app.dependency_overrides[get_wardrobe_repository] = lambda: repository
    app.dependency_overrides[get_vision_provider] = lambda: provider
    app.dependency_overrides[get_r2_storage_client] = lambda: _FakeStorage()
    app.dependency_overrides[get_tag_cache] = _FakeTagCache
    app.dependency_overrides[get_cost_budget_gate] = lambda: (cost_budget_gate or _FakeCostBudgetGate())
    app.dependency_overrides[get_cost_ledger] = lambda: _FakeCostLedgerForRouter()
    app.dependency_overrides[get_app_config_snapshot] = lambda: AppConfigSnapshot()


def test_tag_missing_authorization_header_returns_401() -> None:
    response = client.post("/wardrobe/tag", json={"item_id": VALID_ITEM_ID})

    assert response.status_code == 401


def test_tag_existing_row_returns_202_and_queues_background_task() -> None:
    repository = _FakeRepository(exists=True)
    provider = _FakeVisionProvider()
    _override_tag_infra(repository, provider)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(
            "/wardrobe/tag",
            headers={"Authorization": "Bearer valid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 202
    assert response.json() == {"status": "processing", "item_id": VALID_ITEM_ID}
    mock_add_task.assert_called_once()


def test_tag_nonexistent_row_returns_404_no_background_task_queued() -> None:
    repository = _FakeRepository(exists=False)
    provider = _FakeVisionProvider()
    _override_tag_infra(repository, provider)
    app.dependency_overrides[get_current_user_id] = lambda: "user-2"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(
            "/wardrobe/tag",
            headers={"Authorization": "Bearer valid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 404
    mock_add_task.assert_not_called()
    assert provider.call_count == 0


def test_tag_malformed_item_id_returns_422_not_500() -> None:
    repository = _FakeRepository(exists=True)
    provider = _FakeVisionProvider()
    _override_tag_infra(repository, provider)
    app.dependency_overrides[get_current_user_id] = lambda: "user-3"

    response = client.post(
        "/wardrobe/tag",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": "not-a-uuid"},
    )

    assert response.status_code == 422


# --- SS-029: cost budget gate on POST /wardrobe/tag -------------------------


def test_tag_returns_429_when_budget_exceeded() -> None:
    repository = _FakeRepository(exists=True)
    provider = _FakeVisionProvider()
    gate = _FakeCostBudgetGate(allowed=False, scope="monthly")
    _override_tag_infra(repository, provider, cost_budget_gate=gate)
    app.dependency_overrides[get_current_user_id] = lambda: "user-budget-tag"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(
            "/wardrobe/tag",
            headers={"Authorization": "Bearer valid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 429
    mock_add_task.assert_not_called()
    assert provider.call_count == 0


def test_tag_429_body_is_a_clear_message_not_a_generic_500() -> None:
    repository = _FakeRepository(exists=True)
    provider = _FakeVisionProvider()
    gate = _FakeCostBudgetGate(allowed=False, scope="daily")
    _override_tag_infra(repository, provider, cost_budget_gate=gate)
    app.dependency_overrides[get_current_user_id] = lambda: "user-budget-tag-2"

    response = client.post(
        "/wardrobe/tag",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 429
    body = response.json()
    assert "detail" in body
    assert body["detail"] != "Internal Server Error"
    assert "spending limit" in body["detail"].lower()


def test_request_id_is_minted_once_per_request_and_passed_to_the_task() -> None:
    repository = _FakeRepository(exists=True)
    provider = _FakeVisionProvider()
    gate = _FakeCostBudgetGate(allowed=True)
    _override_tag_infra(repository, provider, cost_budget_gate=gate)
    app.dependency_overrides[get_current_user_id] = lambda: "user-budget-tag-3"

    response = client.post(
        "/wardrobe/tag",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 202
    assert len(gate.reserve_calls) == 1
    assert len(gate.reconcile_calls) == 1


def test_existing_daily_rate_limiter_429_behaviour_is_unchanged() -> None:
    """SS-011 regression guard -- the OLD call-count DailyRateLimiter on
    /remove-bg still enforces its own ceiling independently of the new
    budget gate (design Q4: both coexist, neither ticket retires the
    other)."""
    repository = _FakeRepository(plan_tier="free")
    rate_limiter = _FakeRateLimiter(allowed=False)
    gate = _FakeCostBudgetGate(allowed=True)  # budget would allow -- old limiter still denies
    _override_infra(repository, rate_limiter, cost_budget_gate=gate)
    app.dependency_overrides[get_current_user_id] = lambda: "user-daily-cap"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(
            "/wardrobe/remove-bg",
            headers={"Authorization": "Bearer valid-token"},
            json={"item_id": VALID_ITEM_ID},
        )

    assert response.status_code == 429
    mock_add_task.assert_not_called()
    # The budget gate is never even reached -- the old limiter denies first.
    assert gate.reserve_calls == []


def test_tag_dependency_override_swaps_the_vision_provider() -> None:
    """Mirrors the remove-bg suite's own
    test_dependency_override_swaps_the_background_removal_provider --
    dependency_overrides keys on the exact callable passed to Depends()
    (`get_vision_provider`), not the IVisionProvider ABC directly."""
    repository = _FakeRepository(exists=True)
    counting_provider = _FakeVisionProvider()
    _override_tag_infra(repository, counting_provider)
    app.dependency_overrides[get_current_user_id] = lambda: "user-4"

    response = client.post(
        "/wardrobe/tag",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_id": VALID_ITEM_ID},
    )

    assert response.status_code == 202
    # Background task runs synchronously within TestClient's request call
    # (see module docstring) -- the fake provider was actually invoked.
    assert counting_provider.call_count == 1
    assert len(repository.tagging_updates) == 1
    assert repository.tagging_updates[0]["item_id"] == VALID_ITEM_ID
    assert repository.tagging_updates[0]["tag_columns"]["category"] == "ethnic_kurta"


# --- SS-013: GET /wardrobe/items/{id}/image-url ----------------------------


def _override_image_url_infra(repository: _FakeRepository) -> None:
    app.dependency_overrides[get_wardrobe_repository] = lambda: repository
    app.dependency_overrides[get_r2_storage_client] = lambda: _FakeStorage()


def test_image_url_missing_authorization_header_returns_401() -> None:
    response = client.get(f"/wardrobe/items/{VALID_ITEM_ID}/image-url")

    assert response.status_code == 401


def test_image_url_malformed_item_id_returns_422_not_500() -> None:
    repository = _FakeRepository()
    _override_image_url_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.get(
        "/wardrobe/items/not-a-uuid/image-url",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 422


def test_image_url_nonexistent_or_unowned_item_returns_404() -> None:
    repository = _FakeRepository(image_info=None)
    _override_image_url_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.get(
        f"/wardrobe/items/{VALID_ITEM_ID}/image-url",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 404


def test_image_url_bg_removed_returns_clean_png_presigned_url() -> None:
    repository = _FakeRepository(
        image_info={
            "image_url": f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
            "image_clean_url": f"wardrobe/user-1/{VALID_ITEM_ID}/clean.png",
            "processing_status": "bg_removed",
        }
    )
    _override_image_url_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.get(
        f"/wardrobe/items/{VALID_ITEM_ID}/image-url",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "clean"
    assert "clean.png" in body["url"]


def test_image_url_bg_pending_falls_back_to_original_jpg() -> None:
    repository = _FakeRepository(
        image_info={
            "image_url": f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
            "image_clean_url": None,
            "processing_status": "bg_pending",
        }
    )
    _override_image_url_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.get(
        f"/wardrobe/items/{VALID_ITEM_ID}/image-url",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "original"
    assert "original.jpg" in body["url"]


def test_image_url_no_image_at_all_returns_404() -> None:
    repository = _FakeRepository(
        image_info={
            "image_url": None,
            "image_clean_url": None,
            "processing_status": "uploaded",
        }
    )
    _override_image_url_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.get(
        f"/wardrobe/items/{VALID_ITEM_ID}/image-url",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 404


# --- SS-014: POST /wardrobe/items/image-urls -------------------------------

VALID_ITEM_ID_2 = "22222222-2222-2222-2222-222222222222"
VALID_ITEM_ID_3 = "33333333-3333-3333-3333-333333333333"


def _override_bulk_image_urls_infra(repository: _FakeRepository) -> None:
    app.dependency_overrides[get_wardrobe_repository] = lambda: repository
    app.dependency_overrides[get_r2_storage_client] = lambda: _FakeStorage()


def test_bulk_image_urls_missing_authorization_header_returns_401() -> None:
    response = client.post("/wardrobe/items/image-urls", json={"item_ids": [VALID_ITEM_ID]})

    assert response.status_code == 401


def test_bulk_image_urls_rejects_more_than_200_ids_with_422() -> None:
    repository = _FakeRepository()
    _override_bulk_image_urls_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    too_many_ids = [f"11111111-1111-1111-1111-{i:012d}" for i in range(201)]
    response = client.post(
        "/wardrobe/items/image-urls",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_ids": too_many_ids},
    )

    assert response.status_code == 422


def test_bulk_image_urls_rejects_empty_list_with_422() -> None:
    repository = _FakeRepository()
    _override_bulk_image_urls_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.post(
        "/wardrobe/items/image-urls",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_ids": []},
    )

    assert response.status_code == 422


def test_bulk_image_urls_rejects_malformed_uuid_with_422() -> None:
    repository = _FakeRepository()
    _override_bulk_image_urls_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.post(
        "/wardrobe/items/image-urls",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_ids": ["not-a-uuid"]},
    )

    assert response.status_code == 422


def test_bulk_image_urls_returns_urls_only_for_owned_or_found_ids() -> None:
    # VALID_ITEM_ID_3 is requested but absent from the repository's bulk
    # response (not owned / not found) -- must be silently omitted, not a
    # per-id error (mirrors the single-item endpoint's "not an ownership
    # oracle" precedent).
    repository = _FakeRepository(
        bulk_image_info={
            VALID_ITEM_ID: {
                "image_url": f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
                "image_clean_url": None,
                "thumbnail_url": f"wardrobe/user-1/{VALID_ITEM_ID}/thumbnail.jpg",
                "processing_status": "bg_removed",
            },
            VALID_ITEM_ID_2: {
                "image_url": f"wardrobe/user-1/{VALID_ITEM_ID_2}/original.jpg",
                "image_clean_url": None,
                "thumbnail_url": None,
                "processing_status": "bg_pending",
            },
        }
    )
    _override_bulk_image_urls_infra(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.post(
        "/wardrobe/items/image-urls",
        headers={"Authorization": "Bearer valid-token"},
        json={"item_ids": [VALID_ITEM_ID, VALID_ITEM_ID_2, VALID_ITEM_ID_3]},
    )

    assert response.status_code == 200
    body = response.json()
    urls = body["urls"]
    assert set(urls.keys()) == {VALID_ITEM_ID, VALID_ITEM_ID_2}
    assert urls[VALID_ITEM_ID]["source"] == "thumbnail"
    assert "thumbnail.jpg" in urls[VALID_ITEM_ID]["url"]
    assert urls[VALID_ITEM_ID_2]["source"] == "original"
    assert "original.jpg" in urls[VALID_ITEM_ID_2]["url"]
    assert VALID_ITEM_ID_3 not in urls


# --- SS-015: DELETE /wardrobe/items/{item_id} -------------------------------


class _FakeDeletionService(WardrobeDeletionService):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def cleanup_storage(self, *, user_id: str, item_id: str, keys: list[str]) -> None:
        self.calls.append({"user_id": user_id, "item_id": item_id, "keys": keys})


def _override_delete_infra(
    repository: _FakeRepository, deletion_service: _FakeDeletionService
) -> None:
    app.dependency_overrides[get_wardrobe_repository] = lambda: repository
    app.dependency_overrides[get_deletion_service] = lambda: deletion_service


def test_delete_missing_authorization_header_returns_401() -> None:
    response = client.delete(f"/wardrobe/items/{VALID_ITEM_ID}")

    assert response.status_code == 401


def test_delete_malformed_item_id_returns_422_not_500() -> None:
    repository = _FakeRepository()
    deletion_service = _FakeDeletionService()
    _override_delete_infra(repository, deletion_service)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.delete(
        "/wardrobe/items/not-a-uuid",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 422


def test_delete_nonexistent_or_unowned_item_returns_404_before_any_delete() -> None:
    repository = _FakeRepository(image_info=None)
    deletion_service = _FakeDeletionService()
    _override_delete_infra(repository, deletion_service)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.delete(
            f"/wardrobe/items/{VALID_ITEM_ID}",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 404
    mock_add_task.assert_not_called()
    assert repository.deleted_item_ids == []


def test_delete_row_disappears_between_info_read_and_delete_returns_404() -> None:
    # A defensive edge case: get_item_image_info found the row, but
    # delete_item then reports 0 rows removed (e.g. a concurrent delete of
    # the same item). Must not schedule a cleanup task for keys it never
    # confirmed were actually deleted alongside the row.
    repository = _FakeRepository(
        image_info={
            "image_url": f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
            "image_clean_url": None,
            "thumbnail_url": None,
            "processing_status": "uploaded",
        },
        delete_returns=False,
    )
    deletion_service = _FakeDeletionService()
    _override_delete_infra(repository, deletion_service)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    with patch("routers.wardrobe.BackgroundTasks.add_task") as mock_add_task:
        response = client.delete(
            f"/wardrobe/items/{VALID_ITEM_ID}",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 404
    mock_add_task.assert_not_called()


def test_delete_success_returns_200_and_schedules_cleanup_with_the_rows_three_keys() -> None:
    repository = _FakeRepository(
        image_info={
            "image_url": f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
            "image_clean_url": f"wardrobe/user-1/{VALID_ITEM_ID}/clean.png",
            "thumbnail_url": f"wardrobe/user-1/{VALID_ITEM_ID}/thumbnail.jpg",
            "processing_status": "bg_removed",
        }
    )
    deletion_service = _FakeDeletionService()
    _override_delete_infra(repository, deletion_service)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.delete(
        f"/wardrobe/items/{VALID_ITEM_ID}",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "item_id": VALID_ITEM_ID}
    assert repository.deleted_item_ids == [VALID_ITEM_ID]
    # Background task runs synchronously within TestClient's request call
    # (see module docstring).
    assert len(deletion_service.calls) == 1
    assert deletion_service.calls[0]["item_id"] == VALID_ITEM_ID
    assert set(deletion_service.calls[0]["keys"]) == {
        f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
        f"wardrobe/user-1/{VALID_ITEM_ID}/clean.png",
        f"wardrobe/user-1/{VALID_ITEM_ID}/thumbnail.jpg",
    }


def test_delete_omits_null_keys_from_the_cleanup_call() -> None:
    # image_clean_url/thumbnail_url are null (item never finished bg
    # removal) -- only the non-null original.jpg key is passed through.
    repository = _FakeRepository(
        image_info={
            "image_url": f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg",
            "image_clean_url": None,
            "thumbnail_url": None,
            "processing_status": "uploaded",
        }
    )
    deletion_service = _FakeDeletionService()
    _override_delete_infra(repository, deletion_service)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    response = client.delete(
        f"/wardrobe/items/{VALID_ITEM_ID}",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert deletion_service.calls[0]["keys"] == [f"wardrobe/user-1/{VALID_ITEM_ID}/original.jpg"]
