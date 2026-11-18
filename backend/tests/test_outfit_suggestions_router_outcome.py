"""Tests for POST /outfit-suggestions/outcome (SS-023).

- Requires the REAL, signature-verified ``get_current_user_id`` (never the
  ``/generate`` stub's no-verification behaviour).
- Regression pin (test plan item 5): ``/generate`` still depends on
  ``get_current_user_id_stub`` and ``/portfolio`` still on
  ``get_current_user_id`` -- this ticket must not drift either.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from dependencies.auth import get_current_user_id
from main import app
from routers.outfit_suggestions import get_current_user_id_stub, get_outfit_outcome_service
from services.outfit_outcome_service import OutcomeNotFoundError

client = TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth regression pin
# ---------------------------------------------------------------------------


def test_generate_route_still_uses_the_stub_dependency_unchanged() -> None:
    import inspect

    from routers.outfit_suggestions import generate_outfit_suggestions

    sig = inspect.signature(generate_outfit_suggestions)
    user_id_param = sig.parameters["user_id"]
    assert user_id_param.default.dependency is get_current_user_id_stub


def test_portfolio_route_still_uses_the_real_dependency_unchanged() -> None:
    import inspect

    from routers.outfit_suggestions import generate_outfit_portfolio

    sig = inspect.signature(generate_outfit_portfolio)
    user_id_param = sig.parameters["user_id"]
    assert user_id_param.default.dependency is get_current_user_id


def test_outcome_route_uses_the_real_get_current_user_id_dependency() -> None:
    import inspect

    from routers.outfit_suggestions import record_outfit_outcome

    sig = inspect.signature(record_outfit_outcome)
    user_id_param = sig.parameters["user_id"]
    assert user_id_param.default.dependency is get_current_user_id


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------


def test_missing_authorization_header_returns_401() -> None:
    response = client.post(
        "/outfit-suggestions/outcome",
        json={"session_id": "s1", "rank": 1, "outcome_type": "saved"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_rank_zero_returns_422_before_any_repository_call() -> None:
    class _RaisingService:
        async def record_outcome(self, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("must not be called for an invalid rank")

    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_outcome_service] = lambda: _RaisingService()

    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "s1", "rank": 0, "outcome_type": "saved"},
    )
    assert response.status_code == 422


def test_negative_rank_returns_422() -> None:
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "s1", "rank": -1, "outcome_type": "saved"},
    )
    assert response.status_code == 422


def test_shuffled_away_outcome_type_returns_422_not_in_exposed_literal() -> None:
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "s1", "rank": 1, "outcome_type": "shuffled_away"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Happy path / cross-tenant 404
# ---------------------------------------------------------------------------


class _FakeOutfitOutcomeService:
    def __init__(
        self, result: dict[str, Any] | None = None, *, raise_not_found: bool = False
    ) -> None:
        self._result = result or {
            "outfit_id": "outfit-1",
            "outcome_recorded": True,
            "already_saved": False,
        }
        self._raise_not_found = raise_not_found
        self.calls: list[dict[str, Any]] = []

    async def record_outcome(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raise_not_found:
            raise OutcomeNotFoundError()
        return self._result


def test_happy_path_returns_documented_response_shape() -> None:
    fake_service = _FakeOutfitOutcomeService()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_outcome_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "s1", "rank": 1, "outcome_type": "saved"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"outfit_id": "outfit-1", "outcome_recorded": True, "already_saved": False}
    assert fake_service.calls[0]["user_id"] == "user-1"
    assert fake_service.calls[0]["session_id"] == "s1"
    assert fake_service.calls[0]["rank"] == 1
    assert fake_service.calls[0]["outcome_type"] == "saved"


def test_cross_tenant_or_not_found_returns_404_not_403_not_500() -> None:
    fake_service = _FakeOutfitOutcomeService(raise_not_found=True)
    app.dependency_overrides[get_current_user_id] = lambda: "attacker-user"
    app.dependency_overrides[get_outfit_outcome_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "victims-session", "rank": 1, "outcome_type": "saved"},
    )
    assert response.status_code == 404


def test_dismissed_outfit_id_is_none() -> None:
    fake_service = _FakeOutfitOutcomeService(
        result={"outfit_id": None, "outcome_recorded": True, "already_saved": False}
    )
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_outcome_service] = lambda: fake_service

    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "s1", "rank": 1, "outcome_type": "dismissed"},
    )
    assert response.status_code == 200
    assert response.json()["outfit_id"] is None


def test_service_unexpected_exception_maps_to_500() -> None:
    class _RaisingService:
        async def record_outcome(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("unexpected failure")

    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_outfit_outcome_service] = lambda: _RaisingService()

    response = client.post(
        "/outfit-suggestions/outcome",
        headers={"Authorization": "Bearer any-token"},
        json={"session_id": "s1", "rank": 1, "outcome_type": "saved"},
    )
    assert response.status_code == 500
