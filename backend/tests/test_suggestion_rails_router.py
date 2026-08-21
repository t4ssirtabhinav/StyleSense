"""Tests for GET /suggestion-rails and POST /suggestion-rails/refresh (SS-048).

- ``GET`` is a PURE READ: no ``EngineV2.generate_portfolio`` call, no
  ``BackgroundTasks.add_task`` call (design doc's Router contract).
- A rail whose payload has 0 items is omitted from the response array.
- Both routes use the REAL, signature-verified ``get_current_user_id``
  (same pattern as ``outfit_suggestions.py``'s ``/portfolio``/``/outcome``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from adapters.interfaces import SuggestionRailRow
from dependencies.auth import get_current_user_id
from main import app
from routers.suggestion_rails import get_rail_precompute_service, get_rails_repository

client = TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


class _FakeRailsRepository:
    def __init__(self, rows: list[SuggestionRailRow] | None = None) -> None:
        self._rows = rows or []
        self.get_rails_calls: list[dict[str, Any]] = []

    async def upsert_rails(self, *, jwt: str, user_id: str, rails: list[Any]) -> None:
        raise AssertionError("upsert_rails must not be called directly by the router")

    async def get_rails(self, *, jwt: str, user_id: str) -> list[SuggestionRailRow]:
        self.get_rails_calls.append({"jwt": jwt, "user_id": user_id})
        return self._rows

    async def get_most_recent_computed_at(self, *, jwt: str, user_id: str) -> datetime | None:
        raise AssertionError("get_most_recent_computed_at must not be called by the router")


class _FakePrecomputeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def recompute_all_rails(self, *, jwt: str, user_id: str) -> None:
        self.calls.append({"jwt": jwt, "user_id": user_id})


def _row(rail_key: str, items: list[dict[str, Any]], engine_version: str | None = None) -> SuggestionRailRow:
    return SuggestionRailRow(
        rail_key=rail_key,
        computed_at=datetime(2026, 8, 20, tzinfo=UTC),
        engine_version=engine_version,
        payload={"items": items},
    )


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------


def test_get_missing_authorization_header_returns_401() -> None:
    response = client.get("/suggestion-rails")
    assert response.status_code == 401


def test_refresh_missing_authorization_header_returns_401() -> None:
    response = client.post("/suggestion-rails/refresh")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /suggestion-rails -- pure read
# ---------------------------------------------------------------------------


def test_get_returns_cached_rows_with_no_engine_call_and_no_background_task() -> None:
    from unittest.mock import patch

    fake_repo = _FakeRailsRepository(
        rows=[_row("todays_picks", [{"item_ids": ["i1"], "items": [{"item_id": "i1"}]}], "engine-v2")]
    )
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_rails_repository] = lambda: fake_repo

    with patch(
        "services.engine_v2.EngineV2.generate_portfolio",
        side_effect=AssertionError("must not be called on a pure read"),
    ), patch(
        "fastapi.BackgroundTasks.add_task",
        side_effect=AssertionError("must not schedule a background task on a pure read"),
    ):
        response = client.get(
            "/suggestion-rails", headers={"Authorization": "Bearer any-token"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["rails"][0]["rail_key"] == "todays_picks"
    assert fake_repo.get_rails_calls[0]["user_id"] == "user-1"


def test_get_omits_rails_with_zero_items_from_response() -> None:
    fake_repo = _FakeRailsRepository(
        rows=[
            _row("todays_picks", [{"item_ids": ["i1"], "items": [{"item_id": "i1"}]}], "engine-v2"),
            _row("never_tried_pairs", [], None),
        ]
    )
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_rails_repository] = lambda: fake_repo

    response = client.get("/suggestion-rails", headers={"Authorization": "Bearer any-token"})

    assert response.status_code == 200
    body = response.json()
    keys = [rail["rail_key"] for rail in body["rails"]]
    assert keys == ["todays_picks"]


def test_get_brand_new_user_with_no_rows_returns_empty_array_not_404() -> None:
    fake_repo = _FakeRailsRepository(rows=[])
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_rails_repository] = lambda: fake_repo

    response = client.get("/suggestion-rails", headers={"Authorization": "Bearer any-token"})

    assert response.status_code == 200
    assert response.json() == {"rails": []}


# ---------------------------------------------------------------------------
# POST /suggestion-rails/refresh -- synchronous recompute
# ---------------------------------------------------------------------------


def test_refresh_calls_recompute_then_returns_freshly_written_rows() -> None:
    fake_repo = _FakeRailsRepository(
        rows=[_row("not_yet_worn", [{"item_ids": ["i2"], "items": [{"item_id": "i2"}]}], None)]
    )
    fake_service = _FakePrecomputeService()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_rails_repository] = lambda: fake_repo
    app.dependency_overrides[get_rail_precompute_service] = lambda: fake_service

    response = client.post(
        "/suggestion-rails/refresh", headers={"Authorization": "Bearer any-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rails"][0]["rail_key"] == "not_yet_worn"
    assert fake_service.calls[0]["user_id"] == "user-1"
    assert fake_repo.get_rails_calls[0]["user_id"] == "user-1"


def test_refresh_service_unexpected_exception_maps_to_500() -> None:
    class _RaisingService:
        async def recompute_all_rails(self, **kwargs: Any) -> None:
            raise RuntimeError("unexpected failure")

    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_rail_precompute_service] = lambda: _RaisingService()

    response = client.post(
        "/suggestion-rails/refresh", headers={"Authorization": "Bearer any-token"}
    )
    assert response.status_code == 500
