"""Tests for backend/routers/outfit_suggestions.py (SS-006).

Background-task timing note: verified directly against this repo's installed
fastapi==0.139.0 / starlette==1.3.1 (see docs/worklog/SS-006.md) that
TestClient's request call executes `BackgroundTasks` synchronously -- the
task's side effect is observable immediately after the request call
returns, no polling/synchronization primitive needed.
"""

from __future__ import annotations

import jwt
from fastapi.testclient import TestClient

from ai.adapters.mock_styling_adapter import MockStylingAdapter
from ai.ports.interfaces import (
    IStylingProvider,
    NarratedPortfolioResult,
    OutfitSuggestionItem,
    OutfitSuggestionResult,
    StylePreferencesInput,
)
from main import app
from routers.outfit_suggestions import get_styling_provider
from services.styling_router import StylingRouter

client = TestClient(app)


def _make_stub_token(sub: str = "user-abc-123") -> str:
    # Signature is never verified by the stub dependency -- any secret works.
    return jwt.encode({"sub": sub}, "any-secret-not-verified", algorithm="HS256")


class _FakeCallTrackingProvider(IStylingProvider):
    def __init__(self) -> None:
        self.call_count = 0

    async def suggest_outfits(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> OutfitSuggestionResult:
        self.call_count += 1
        return OutfitSuggestionResult(
            user_id="",
            suggestions=[
                OutfitSuggestionItem(
                    item_category="western_top",
                    label="Fake Override Item",
                    rationale="from the overridden fake adapter",
                )
            ],
            generated_at="2026-07-23T00:00:00+00:00",
            is_personalized=True,
            source="mock",
        )

    async def narrate_candidates(
        self,
        candidates: list[dict[str, object]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        weather: dict[str, object] | None = None,
    ) -> NarratedPortfolioResult:
        return NarratedPortfolioResult(narrations=[], language="en", source="rules_only")


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_valid_stub_token_returns_202_with_queued_status() -> None:
    token = _make_stub_token()

    response = client.post(
        "/outfit-suggestions/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"style_preferences": None},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["user_id"] == "user-abc-123"


def test_missing_authorization_header_returns_401() -> None:
    response = client.post("/outfit-suggestions/generate", json={})

    assert response.status_code == 401


def test_malformed_authorization_header_returns_401() -> None:
    response = client.post(
        "/outfit-suggestions/generate",
        headers={"Authorization": "not-a-bearer-token"},
        json={},
    )

    assert response.status_code == 401


def test_garbage_bearer_token_returns_401() -> None:
    response = client.post(
        "/outfit-suggestions/generate",
        headers={"Authorization": "Bearer not.a.jwt"},
        json={},
    )

    assert response.status_code == 401


def test_dependency_override_swaps_the_styling_provider() -> None:
    fake_provider = _FakeCallTrackingProvider()
    app.dependency_overrides[get_styling_provider] = lambda: fake_provider

    token = _make_stub_token()
    response = client.post(
        "/outfit-suggestions/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"style_preferences": {"gender": "woman"}},
    )

    assert response.status_code == 202
    # Background task runs synchronously under this installed fastapi/starlette
    # version (verified via probe -- see worklog), so this is observable now.
    assert fake_provider.call_count == 1


class _CallCountingMockAdapter(IStylingProvider):
    """Wraps the real MockStylingAdapter so the test can both assert an
    invocation count AND exercise the real (mock) suggestion logic."""

    def __init__(self) -> None:
        self._delegate = MockStylingAdapter()
        self.call_count = 0

    async def suggest_outfits(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> OutfitSuggestionResult:
        self.call_count += 1
        return await self._delegate.suggest_outfits(preferences, max_suggestions=max_suggestions)

    async def narrate_candidates(
        self,
        candidates: list[dict[str, object]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        weather: dict[str, object] | None = None,
    ) -> NarratedPortfolioResult:
        return await self._delegate.narrate_candidates(
            candidates,
            occasion=occasion,
            preferences=preferences,
            max_suggestions=max_suggestions,
            weather=weather,
        )


def test_mock_provider_invoked_exactly_once_after_request_completes() -> None:
    counting_adapter = _CallCountingMockAdapter()
    app.dependency_overrides[get_styling_provider] = lambda: counting_adapter

    token = _make_stub_token()
    response = client.post(
        "/outfit-suggestions/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"style_preferences": {"styles": ["ethnic"]}},
    )

    assert response.status_code == 202
    # Background task runs synchronously under this installed fastapi/
    # starlette version (verified via probe -- see worklog), so this is
    # observable immediately after the request call returns.
    assert counting_adapter.call_count == 1


def test_get_styling_provider_now_takes_di_helper_dependencies() -> None:
    """(SS-028) get_styling_provider() is no longer the SS-006 zero-argument
    stub that always returned MockStylingAdapter() -- it now composes a
    StylingRouter from several Depends()-injected helpers (proven directly
    below via the real composition path)."""
    import inspect

    from fastapi.params import Depends as DependsMarker

    sig = inspect.signature(get_styling_provider)
    assert len(sig.parameters) >= 4
    assert all(isinstance(p.default, DependsMarker) for p in sig.parameters.values())


async def test_real_composition_path_builds_a_styling_router_instance() -> None:
    """Exercises get_styling_provider's real dependency chain end-to-end
    (no override), proving the object it hands back is a StylingRouter, not
    the pre-SS-028 MockStylingAdapter stub."""
    from routers.outfit_suggestions import (
        get_provider_quota_tracker,
        get_routing_context,
        get_routing_mix_monitor,
        get_styling_provider_registry,
    )
    from services.app_config import AppConfigSnapshot

    snapshot = AppConfigSnapshot(values={}, fetched_at=0.0, stale=True)
    registry = get_styling_provider_registry()
    quota = get_provider_quota_tracker(snapshot)
    monitor = get_routing_mix_monitor(snapshot)
    context = get_routing_context(user_id="user-xyz")

    provider = get_styling_provider(
        snapshot=snapshot,
        registry=registry,
        quota=quota,
        monitor=monitor,
        context=context,
    )

    assert isinstance(provider, StylingRouter)
