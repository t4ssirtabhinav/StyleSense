"""Tests for backend/adapters/fabric_registry_repository.py (SS-038),
mocked ``supabase-py`` async client -- no real network/DB calls.

Mirrors test_app_config_repository.py's fake-``AsyncClient``-builder style.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.fabric_registry_repository import SupabaseFabricRegistryRepository

FABRIC_ROWS = [
    {"key": "cotton", "weight": "light", "breathability": 9, "season_affinity": ["summer"]},
    {"key": "silk", "weight": "medium", "breathability": 5, "season_affinity": None},
]


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(self, response_data: Any) -> None:
        self._response_data = response_data

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
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
        "adapters.fabric_registry_repository.acreate_client",
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
    fake_client = _FakeAsyncClient(FABRIC_ROWS)

    with _patch_acreate_client(fake_client) as mocked:
        await SupabaseFabricRegistryRepository().fetch_all()

    mocked.assert_awaited_once()
    call_args = mocked.call_args
    assert call_args.args[1] == "service-role-key"
    assert "anon-key" not in call_args.args


async def test_maps_rows_into_a_key_to_fabricattributes_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(FABRIC_ROWS)

    with _patch_acreate_client(fake_client):
        result = await SupabaseFabricRegistryRepository().fetch_all()

    assert set(result) == {"cotton", "silk"}
    assert result["cotton"].weight == "light"
    assert result["cotton"].breathability == 9
    assert result["cotton"].season_affinity == ("summer",)
    # silk's season_affinity IS NULL -- BL-125's flagged row, structural
    # "no seasonal opinion", not an empty tuple.
    assert result["silk"].season_affinity is None


async def test_zero_rows_resolve_to_an_empty_dict_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(None)

    with _patch_acreate_client(fake_client):
        result = await SupabaseFabricRegistryRepository().fetch_all()

    assert result == {}


async def test_propagates_on_transport_failure_per_the_port_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)

    with patch(
        "adapters.fabric_registry_repository.acreate_client",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        with pytest.raises(RuntimeError):
            await SupabaseFabricRegistryRepository().fetch_all()
