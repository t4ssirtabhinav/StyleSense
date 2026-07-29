"""Tests for backend/adapters/app_config_repository.py (SS-026), mocked
``supabase-py`` async client -- no real network/DB calls.

Mirrors test_occasion_repository.py's fake-``AsyncClient``-builder style,
INVERTED assertion: this repository's whole contract is to use
``service_role``, the opposite of every other repository in this codebase.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.app_config_repository import SupabaseAppConfigRepository

CONFIG_ROWS = [
    {"key": "config_cache_ttl_seconds", "value": {"seconds": 60}},
    {"key": "gemini_quota_ceiling_rpm", "value": {"rpm": 15}},
]


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(self, response_data: Any) -> None:
        self._response_data = response_data

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self

    async def execute(self) -> _FakeResponse:
        return _FakeResponse(self._response_data)


class _FakeAsyncClient:
    def __init__(self, response_data: Any) -> None:
        self.table_names: list[str] = []
        self._response_data = response_data

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_names.append(name)
        return _FakeQueryBuilder(self._response_data)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.app_config_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


async def test_builds_its_client_with_service_role_not_anon_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(CONFIG_ROWS)

    with _patch_acreate_client(fake_client) as mocked:
        await SupabaseAppConfigRepository().fetch_all()

    # Opposite assertion from test_occasion_repository.py's "never
    # service_role" -- here it must be present, and the anon key must not
    # be used at all.
    mocked.assert_awaited_once()
    call_args = mocked.call_args
    assert call_args.args[1] == "service-role-key"
    assert "anon-key" not in call_args.args


async def test_maps_rows_into_a_key_value_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(CONFIG_ROWS)

    with _patch_acreate_client(fake_client):
        result = await SupabaseAppConfigRepository().fetch_all()

    assert result == {
        "config_cache_ttl_seconds": {"seconds": 60},
        "gemini_quota_ceiling_rpm": {"rpm": 15},
    }


async def test_zero_rows_resolve_to_an_empty_dict_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(None)

    with _patch_acreate_client(fake_client):
        result = await SupabaseAppConfigRepository().fetch_all()

    assert result == {}
