"""Tests for backend/adapters/outfit_repository.py.

Deviation note (SS-048): no test file existed for
``SupabaseOutfitRepository`` before this ticket -- created fresh rather than
"modified", mirroring ``test_wardrobe_repository.py``'s fake-client pattern.
Only covers ``get_item_ids_for_user`` (SS-048's new method); the pre-existing
``insert_outfit``/``insert_wear_rows`` methods are out of this ticket's scope
and not retroactively covered here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.outfit_repository import SupabaseOutfitRepository


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

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("select", *args, **kwargs)

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("eq", *args, **kwargs)

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
        "adapters.outfit_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


async def test_get_item_ids_for_user_returns_one_array_per_outfits_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(
        response_data=[
            {"item_ids": ["a", "b"]},
            {"item_ids": ["c", "d", "e"]},
        ]
    )
    repo = SupabaseOutfitRepository()

    with _patch_acreate_client(fake_client):
        rows = await repo.get_item_ids_for_user(jwt="caller-jwt", user_id="user-1")

    assert rows == [["a", "b"], ["c", "d", "e"]]
    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["outfits"]
    select_call = next(c for c in fake_client.calls if c[0] == "select")
    assert select_call[1][0] == "item_ids"


async def test_get_item_ids_for_user_returns_empty_list_for_no_outfits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseOutfitRepository()

    with _patch_acreate_client(fake_client):
        rows = await repo.get_item_ids_for_user(jwt="caller-jwt", user_id="user-1")

    assert rows == []


async def test_get_item_ids_for_user_treats_null_item_ids_as_empty_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[{"item_ids": None}])
    repo = SupabaseOutfitRepository()

    with _patch_acreate_client(fake_client):
        rows = await repo.get_item_ids_for_user(jwt="caller-jwt", user_id="user-1")

    assert rows == [[]]
