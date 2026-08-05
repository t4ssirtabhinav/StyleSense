"""Tests for backend/adapters/wear_history_repository.py (SS-035), mocked
``supabase-py`` async client -- no real network/DB calls.

Mirrors test_occasion_repository.py's fake-builder style, including its
load-bearing "anon key + caller JWT, never service_role" assertion, plus a
fake ``.rpc()`` builder (this port's calls are RPC, not table reads).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.wear_history_repository import SupabaseWearHistoryRepository


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeRpcBuilder:
    def __init__(self, response_data: Any, raise_exc: Exception | None) -> None:
        self._response_data = response_data
        self._raise_exc = raise_exc

    async def execute(self) -> _FakeResponse:
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_data)


class _FakePostgrest:
    def __init__(self) -> None:
        self.auth_calls: list[str] = []

    def auth(self, jwt: str) -> None:
        self.auth_calls.append(jwt)


class _FakeAsyncClient:
    def __init__(
        self, response_data: Any = None, raise_exc: Exception | None = None
    ) -> None:
        self.postgrest = _FakePostgrest()
        self.rpc_calls: list[tuple[str, dict[str, Any] | None]] = []
        self._response_data = response_data
        self._raise_exc = raise_exc

    def rpc(self, fn: str, params: dict[str, Any] | None = None) -> _FakeRpcBuilder:
        self.rpc_calls.append((fn, params))
        return _FakeRpcBuilder(self._response_data, self._raise_exc)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.wear_history_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    # Deliberately present, so the "never service_role" assertion below is
    # meaningful rather than vacuous.
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


async def test_uses_anon_key_with_the_callers_jwt_not_service_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client) as mocked:
        await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    for call in mocked.call_args_list:
        assert call.args[1] == "anon-key"
        assert "service-role-key" not in call.args


async def test_calls_the_wear_recency_rpc_with_both_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client):
        await repo.fetch_wear_recency(
            jwt="caller-jwt", user_id="user-1", occasion_key="office"
        )

    assert fake_client.rpc_calls == [
        ("wear_recency", {"p_user_id": "user-1", "p_occasion_key": "office"})
    ]


async def test_sends_a_null_occasion_key_explicitly_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client):
        await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert fake_client.rpc_calls == [
        ("wear_recency", {"p_user_id": "user-1", "p_occasion_key": None})
    ]


async def test_maps_every_field_including_null_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(
        response_data=[
            {
                "item_id": "item-1",
                "last_worn_on": "2026-07-20",
                "last_worn_on_for_occasion": None,
                "wears_for_occasion": 0,
            }
        ]
    )
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert len(result) == 1
    entry = result[0]
    assert entry.item_id == "item-1"
    assert entry.last_worn_on is not None and entry.last_worn_on.isoformat() == "2026-07-20"
    assert entry.last_worn_on_for_occasion is None
    assert entry.wears_for_occasion == 0


async def test_returns_empty_list_on_db_error_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(raise_exc=RuntimeError("boom"))
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert result == []


async def test_returns_empty_list_when_client_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    repo = SupabaseWearHistoryRepository()

    with patch(
        "adapters.wear_history_repository.acreate_client",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result = await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert result == []


async def test_returns_empty_list_for_a_user_with_no_wears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert result == []


async def test_wears_for_occasion_is_zero_not_none_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(
        response_data=[
            {
                "item_id": "item-1",
                "last_worn_on": "2026-07-20",
                "last_worn_on_for_occasion": None,
                "wears_for_occasion": None,
            }
        ]
    )
    repo = SupabaseWearHistoryRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.fetch_wear_recency(jwt="caller-jwt", user_id="user-1")

    assert result[0].wears_for_occasion == 0
    assert isinstance(result[0].wears_for_occasion, int)
