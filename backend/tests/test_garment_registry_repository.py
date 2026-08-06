"""Tests for backend/adapters/garment_registry_repository.py (SS-038),
mocked ``supabase-py`` async client -- no real network/DB calls.

Mirrors test_app_config_repository.py's fake-``AsyncClient``-builder style,
same assertion shape: this repository's whole contract is to use
``service_role`` (see module docstring for the deliberate deviation
justification).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.garment_registry_repository import SupabaseGarmentRegistryRepository

GARMENT_TYPE_ROWS = [
    {
        "key": "kurta",
        "slot": "torso_base",
        "layer": 0,
        "register": ["ethnic"],
        "base_formality": 4,
        "pairs_with": ["ethnic_bottom"],
        "requires_with": None,
        "excludes_with": None,
        "styling_rules": {"volume_class": "fitted"},
    }
]
ALIAS_ROWS = [{"alias": "plazo", "garment_key": "palazzo"}]


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
    def __init__(self, types_data: Any, aliases_data: Any) -> None:
        self.table_names: list[str] = []
        self._types_data = types_data
        self._aliases_data = aliases_data

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_names.append(name)
        if name == "garment_types":
            return _FakeQueryBuilder(self._types_data)
        return _FakeQueryBuilder(self._aliases_data)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.garment_registry_repository.acreate_client",
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
    fake_client = _FakeAsyncClient(GARMENT_TYPE_ROWS, ALIAS_ROWS)

    with _patch_acreate_client(fake_client) as mocked:
        await SupabaseGarmentRegistryRepository().fetch_registry()

    mocked.assert_awaited_once()
    call_args = mocked.call_args
    assert call_args.args[1] == "service-role-key"
    assert "anon-key" not in call_args.args


async def test_maps_rows_into_a_snapshot_with_rows_and_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(GARMENT_TYPE_ROWS, ALIAS_ROWS)

    with _patch_acreate_client(fake_client):
        snapshot = await SupabaseGarmentRegistryRepository().fetch_registry()

    assert set(fake_client.table_names) == {"garment_types", "garment_type_aliases"}
    assert "kurta" in snapshot.rows
    row = snapshot.rows["kurta"]
    assert row.slot == "torso_base"
    assert row.register == ("ethnic",)
    assert row.pairs_with == ("ethnic_bottom",)
    assert row.requires_with == ()
    assert row.styling_rules == {"volume_class": "fitted"}
    assert snapshot.aliases == {"plazo": "palazzo"}


async def test_zero_rows_resolve_to_an_empty_snapshot_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(None, None)

    with _patch_acreate_client(fake_client):
        snapshot = await SupabaseGarmentRegistryRepository().fetch_registry()

    assert snapshot.rows == {}
    assert snapshot.aliases == {}


async def test_propagates_on_transport_failure_per_the_port_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike IWearHistoryRepository, this port RAISES on failure --
    GarmentRegistryAdapter owns the stale-or-empty-serving fallback policy,
    not this repository."""
    _set_env(monkeypatch)

    with patch(
        "adapters.garment_registry_repository.acreate_client",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        with pytest.raises(RuntimeError):
            await SupabaseGarmentRegistryRepository().fetch_registry()
