"""Tests for backend/adapters/occasion_repository.py (SS-025), mocked
``supabase-py`` async client -- no real network/DB calls.

Mirrors test_wardrobe_repository.py's fake-builder style, including its
load-bearing "anon key + caller JWT, never service_role" assertion.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.occasion_repository import SupabaseOccasionRepository

OCCASION_ROWS = [
    {
        "key": "office",
        "label": "Office",
        "badge_color": "office",
        "kind": "professional",
        "parent_key": None,
        "sort_order": 1,
    },
    {
        "key": "casual",
        "label": "Casual",
        "badge_color": "casual",
        "kind": "everyday",
        "parent_key": None,
        "sort_order": 2,
    },
]

ALIAS_ROWS = [
    {"alias": "wedding", "occasion_key": "wedding_guest"},
    {"alias": "date", "occasion_key": "date_night"},
]


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(
        self,
        calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]],
        response_data: Any,
    ) -> None:
        self._calls = calls
        self._response_data = response_data

    def _record(self, name: str, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._calls.append((name, args, kwargs))
        return self

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("select", *args, **kwargs)

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("eq", *args, **kwargs)

    def order(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("order", *args, **kwargs)

    async def execute(self) -> _FakeResponse:
        self._calls.append(("execute", (), {}))
        return _FakeResponse(self._response_data)


class _FakePostgrest:
    def __init__(self) -> None:
        self.auth_calls: list[str] = []

    def auth(self, jwt: str) -> None:
        self.auth_calls.append(jwt)


class _FakeAsyncClient:
    def __init__(self, response_by_table: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.postgrest = _FakePostgrest()
        self.table_names: list[str] = []
        self._response_by_table = response_by_table or {}

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_names.append(name)
        return _FakeQueryBuilder(self.calls, self._response_by_table.get(name, []))


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.occasion_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    # Deliberately present, so the "never service_role" assertion below is
    # meaningful rather than vacuous.
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


async def test_builds_its_client_with_the_anon_key_and_caller_jwt_never_service_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient({"occasions": OCCASION_ROWS, "occasion_aliases": ALIAS_ROWS})
    repo = SupabaseOccasionRepository()

    with _patch_acreate_client(fake_client) as mocked:
        await repo.fetch_registry(jwt="caller-jwt")

    # postgrest.auth() carries the CALLER's token, so the
    # authenticated_read_occasions RLS policy stays in the loop. One client
    # is built per fetch_registry() call and reused for both table reads.
    assert fake_client.postgrest.auth_calls == ["caller-jwt"]

    for call in mocked.call_args_list:
        assert call.args[1] == "anon-key"
        assert "service-role-key" not in call.args


async def test_reads_only_active_rows_ordered_by_sort_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient({"occasions": OCCASION_ROWS, "occasion_aliases": ALIAS_ROWS})

    with _patch_acreate_client(fake_client):
        await SupabaseOccasionRepository().fetch_registry(jwt="caller-jwt")

    assert fake_client.table_names == ["occasions", "occasion_aliases"]

    eq_calls = [c for c in fake_client.calls if c[0] == "eq"]
    assert eq_calls == [("eq", ("is_active", True), {})]

    order_calls = [c for c in fake_client.calls if c[0] == "order"]
    assert order_calls == [("order", ("sort_order",), {"desc": False})]


async def test_maps_rows_into_a_snapshot_preserving_sort_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient({"occasions": OCCASION_ROWS, "occasion_aliases": ALIAS_ROWS})

    with _patch_acreate_client(fake_client):
        snapshot = await SupabaseOccasionRepository().fetch_registry(jwt="caller-jwt")

    assert snapshot.keys == ("office", "casual")
    assert snapshot.aliases == {"wedding": "wedding_guest", "date": "date_night"}
    assert snapshot.labels == {"office": "Office", "casual": "Casual"}
    assert snapshot.badge_colors == {"office": "office", "casual": "casual"}


async def test_zero_rows_resolve_to_an_empty_snapshot_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient({"occasions": None, "occasion_aliases": None})

    with _patch_acreate_client(fake_client):
        snapshot = await SupabaseOccasionRepository().fetch_registry(jwt="caller-jwt")

    assert snapshot.keys == ()
    assert snapshot.aliases == {}
