"""Tests for backend/adapters/suggestion_rails_repository.py (SS-048),
mocked ``supabase-py`` async client -- no real network/DB calls. Mirrors
``test_wardrobe_repository.py``/``test_outfit_repository.py``'s fake-client
pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.interfaces import SuggestionRailUpsert
from adapters.suggestion_rails_repository import SupabaseSuggestionRailsRepository


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(
        self, calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]], response_data: Any
    ) -> None:
        self._calls = calls
        self._response_data = response_data

    def _record(self, name: str, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._calls.append((name, args, kwargs))
        return self

    def upsert(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("upsert", *args, **kwargs)

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("select", *args, **kwargs)

    def order(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("order", *args, **kwargs)

    def limit(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("limit", *args, **kwargs)

    async def execute(self) -> _FakeResponse:
        self._calls.append(("execute", (), {}))
        return _FakeResponse(self._response_data)


class _FakePostgrest:
    def __init__(self) -> None:
        self.auth_calls: list[str] = []

    def auth(self, jwt: str) -> None:
        self.auth_calls.append(jwt)


class _FakeAsyncClient:
    def __init__(self, response_data: Any = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.postgrest = _FakePostgrest()
        self._response_data = response_data
        self.table_names: list[str] = []

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_names.append(name)
        return _FakeQueryBuilder(self.calls, self._response_data)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.suggestion_rails_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


async def test_upsert_rails_writes_one_row_per_rail_on_conflict_user_rail_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseSuggestionRailsRepository()

    rails = [
        SuggestionRailUpsert(
            rail_key="todays_picks", engine_version="engine-v2", payload={"items": []}
        ),
        SuggestionRailUpsert(
            rail_key="not_yet_worn", engine_version=None, payload={"items": []}
        ),
    ]

    with _patch_acreate_client(fake_client):
        await repo.upsert_rails(jwt="caller-jwt", user_id="user-1", rails=rails)

    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["suggestion_rails"]
    upsert_call = next(c for c in fake_client.calls if c[0] == "upsert")
    payload = upsert_call[1][0]
    assert len(payload) == 2
    assert payload[0]["user_id"] == "user-1"
    assert payload[0]["rail_key"] == "todays_picks"
    assert payload[0]["engine_version"] == "engine-v2"
    assert payload[1]["rail_key"] == "not_yet_worn"
    assert payload[1]["engine_version"] is None
    assert upsert_call[2]["on_conflict"] == "user_id,rail_key"


async def test_upsert_rails_is_a_noop_for_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient()
    repo = SupabaseSuggestionRailsRepository()

    with _patch_acreate_client(fake_client):
        await repo.upsert_rails(jwt="caller-jwt", user_id="user-1", rails=[])

    assert fake_client.calls == []
    assert fake_client.table_names == []


async def test_get_rails_returns_rows_mapped_to_suggestion_rail_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(
        response_data=[
            {
                "rail_key": "todays_picks",
                "computed_at": "2026-08-20T10:00:00Z",
                "engine_version": "engine-v2",
                "payload": {"items": [{"item_ids": ["a"]}]},
            }
        ]
    )
    repo = SupabaseSuggestionRailsRepository()

    with _patch_acreate_client(fake_client):
        rows = await repo.get_rails(jwt="caller-jwt", user_id="user-1")

    assert len(rows) == 1
    assert rows[0].rail_key == "todays_picks"
    assert rows[0].engine_version == "engine-v2"
    assert rows[0].payload == {"items": [{"item_ids": ["a"]}]}
    assert rows[0].computed_at == datetime(2026, 8, 20, 10, 0, 0, tzinfo=UTC)


async def test_get_rails_returns_empty_list_for_brand_new_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseSuggestionRailsRepository()

    with _patch_acreate_client(fake_client):
        rows = await repo.get_rails(jwt="caller-jwt", user_id="user-1")

    assert rows == []


async def test_get_most_recent_computed_at_returns_max_across_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[{"computed_at": "2026-08-20T10:00:00Z"}])
    repo = SupabaseSuggestionRailsRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.get_most_recent_computed_at(jwt="caller-jwt", user_id="user-1")

    assert result == datetime(2026, 8, 20, 10, 0, 0, tzinfo=UTC)
    order_call = next(c for c in fake_client.calls if c[0] == "order")
    assert order_call[1] == ("computed_at",)
    assert order_call[2]["desc"] is True


async def test_get_most_recent_computed_at_returns_none_when_no_rows_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseSuggestionRailsRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.get_most_recent_computed_at(jwt="caller-jwt", user_id="user-1")

    assert result is None
