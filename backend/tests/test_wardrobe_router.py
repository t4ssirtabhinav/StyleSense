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

from adapters.interfaces import IWardrobeRepository
from ai.ports.interfaces import BackgroundRemovalResult, IBackgroundRemovalProvider
from dependencies.auth import get_current_user_id
from main import app
from routers.wardrobe import (
    get_background_removal_provider,
    get_circuit_breaker,
    get_daily_rate_limiter,
    get_r2_storage_client,
    get_wardrobe_repository,
)

client = TestClient(app)

VALID_ITEM_ID = "11111111-1111-1111-1111-111111111111"


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (100, 100), (20, 40, 60))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeRepository(IWardrobeRepository):
    def __init__(self, plan_tier: str = "free") -> None:
        self.plan_tier = plan_tier
        self.upserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

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


class _FakeCircuitBreaker:
    async def is_open(self) -> bool:
        return False

    async def record_success(self) -> None:
        pass

    async def record_failure(self) -> None:
        pass


def teardown_function() -> None:
    app.dependency_overrides.clear()


def _override_infra(repository: _FakeRepository, rate_limiter: _FakeRateLimiter) -> None:
    app.dependency_overrides[get_wardrobe_repository] = lambda: repository
    app.dependency_overrides[get_daily_rate_limiter] = lambda: rate_limiter
    app.dependency_overrides[get_background_removal_provider] = lambda: _FakeProvider()
    app.dependency_overrides[get_r2_storage_client] = lambda: _FakeStorage()
    app.dependency_overrides[get_circuit_breaker] = lambda: _FakeCircuitBreaker()


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
