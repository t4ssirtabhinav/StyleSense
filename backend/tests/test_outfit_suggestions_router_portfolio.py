"""Tests for POST /outfit-suggestions/portfolio (SS-020).

- Requires the REAL, signature-verified ``get_current_user_id`` -- a
  malformed/unsigned token gets 401 (never the ``/generate`` stub's
  no-verification behaviour).
- Regression pin: the pre-existing ``/generate`` route and its
  ``get_current_user_id_stub`` auth are byte-identical, unchanged by this
  ticket.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dependencies.auth import get_current_user_id
from main import app
from routers.outfit_suggestions import get_current_user_id_stub, get_outfit_portfolio_service

client = TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth regression pin -- the pre-existing /generate route is untouched.
# ---------------------------------------------------------------------------


def test_generate_route_still_uses_the_stub_dependency_unchanged() -> None:
    import inspect

    from routers.outfit_suggestions import generate_outfit_suggestions

    sig = inspect.signature(generate_outfit_suggestions)
    user_id_param = sig.parameters["user_id"]
    # The dependency default is a fastapi.params.Depends wrapping
    # get_current_user_id_stub -- proven by identity, not just import.
    assert user_id_param.default.dependency is get_current_user_id_stub


def test_portfolio_route_uses_the_real_get_current_user_id_dependency() -> None:
    import inspect

    from routers.outfit_suggestions import generate_outfit_portfolio

    sig = inspect.signature(generate_outfit_portfolio)
    user_id_param = sig.parameters["user_id"]
    assert user_id_param.default.dependency is get_current_user_id


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------


def test_missing_authorization_header_returns_401() -> None:
    response = client.post("/outfit-suggestions/portfolio", json={"occasion": "office"})
    assert response.status_code == 401


def test_malformed_or_unsigned_token_returns_401_via_real_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    with patch("dependencies.auth.create_client") as mock_create_client:
        mock_create_client.return_value.auth.get_user.side_effect = RuntimeError("invalid")

        response = client.post(
            "/outfit-suggestions/portfolio",
            headers={"Authorization": "Bearer some-invalid-token"},
            json={"occasion": "office"},
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Happy path (dependency-overridden service)
# ---------------------------------------------------------------------------


class _FakeOutfitPortfolioService:
    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def generate_portfolio_for_request(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self._result


def _valid_response_payload() -> dict[str, Any]:
    return {
        "portfolio": [
            {
                "item_ids": ["a", "b"],
                "category_labels": {"a": "western_top", "b": "western_bottom"},
                "total_score": 0.85,
                "rationale": "a solid pick for the office",
                "rationale_language": "en",
                "is_exploration": False,
                "gap_flags": [],
                # (SS-023) additive fields
                "rank": 1,
                "outfit_fingerprint": "a" * 64,
            }
        ],
        "limited_options": False,
        "gap_report": {"excluded_missing_color_or_category": 0, "missing_slots": []},
        "engine_version": "engine-v2",
        "effort_tier": "E2",
        "cache_hit": False,
        "generated_at": "2026-08-07T00:00:00+00:00",
        # (SS-023) additive fields
        "session_id": "session-1",
        "occasion_key": "office",
    }


def test_end_to_end_happy_path_returns_200_with_documented_response_shape() -> None:
    fake_service = _FakeOutfitPortfolioService(_valid_response_payload())
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_portfolio_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/portfolio",
        headers={"Authorization": "Bearer any-token"},
        json={"occasion": "office"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["engine_version"] == "engine-v2"
    assert body["effort_tier"] == "E2"
    assert body["cache_hit"] is False
    assert len(body["portfolio"]) == 1
    assert body["portfolio"][0]["item_ids"] == ["a", "b"]
    assert fake_service.calls[0]["user_id"] == "user-1"
    assert fake_service.calls[0]["occasion"] == "office"


def test_zero_item_portfolio_still_returns_200_not_404() -> None:
    payload = _valid_response_payload()
    payload["portfolio"] = []
    payload["limited_options"] = True
    fake_service = _FakeOutfitPortfolioService(payload)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_portfolio_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/portfolio",
        headers={"Authorization": "Bearer any-token"},
        json={"occasion": "office"},
    )

    assert response.status_code == 200
    assert response.json()["portfolio"] == []
    assert response.json()["limited_options"] is True


def test_service_exception_maps_to_500_not_a_silent_200() -> None:
    class _RaisingService:
        async def generate_portfolio_for_request(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("unexpected failure")

    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_portfolio_service] = lambda: _RaisingService()

    response = client.post(
        "/outfit-suggestions/portfolio",
        headers={"Authorization": "Bearer any-token"},
        json={"occasion": "office"},
    )

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# SS-022 -- weather block: validates with `weather` present and with
# `weather=None`; a request from a user with no city returns 200 with
# `weather: null`.
# ---------------------------------------------------------------------------


def test_response_validates_with_weather_present() -> None:
    payload = _valid_response_payload()
    payload["weather"] = {
        "city": "Mumbai",
        "temp_c": 28.4,
        "condition": "partly_cloudy",
        "humidity": 71,
        "is_heavy_rain": False,
    }
    fake_service = _FakeOutfitPortfolioService(payload)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_portfolio_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/portfolio",
        headers={"Authorization": "Bearer any-token"},
        json={"occasion": "office"},
    )

    assert response.status_code == 200
    assert response.json()["weather"] == {
        "city": "Mumbai",
        "temp_c": 28.4,
        "condition": "partly_cloudy",
        "humidity": 71,
        "is_heavy_rain": False,
    }


def test_response_validates_with_weather_none_no_city_user() -> None:
    """A missing weather field never blanks the screen -- the response is
    otherwise byte-identical to pre-SS-022 output."""
    payload = _valid_response_payload()
    payload["weather"] = None
    fake_service = _FakeOutfitPortfolioService(payload)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_portfolio_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/portfolio",
        headers={"Authorization": "Bearer any-token"},
        json={"occasion": "office"},
    )

    assert response.status_code == 200
    assert response.json()["weather"] is None


def test_response_validates_with_weather_key_absent_entirely() -> None:
    """The Pydantic field default (None) covers a caller that omits the key
    outright -- pre-SS-022 payload shape must still validate."""
    payload = _valid_response_payload()
    assert "weather" not in payload
    fake_service = _FakeOutfitPortfolioService(payload)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_portfolio_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/portfolio",
        headers={"Authorization": "Bearer any-token"},
        json={"occasion": "office"},
    )

    assert response.status_code == 200
    assert response.json()["weather"] is None
