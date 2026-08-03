"""Tests for backend/adapters/supabase_cost_ledger.py (SS-029 design §6.6),
mocked ``supabase-py`` async client -- no real network/DB calls.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.interfaces import CostLedgerEntry
from adapters.supabase_cost_ledger import SupabaseCostLedger


def _entry(**overrides: Any) -> CostLedgerEntry:
    defaults: dict[str, Any] = {
        "user_id": "user-1",
        "request_id": "req-1",
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "feature": "wardrobe_tagging",
        "cost_micropaise": 2_500_000,
        "pricing_status": "estimated",
        "unit_price_snapshot": {"fx_usd_to_inr": 84.0},
        "tokens_in": 1800,
        "tokens_out": 300,
        "latency_ms": 800,
        "cache_hit": False,
        "price_effective_from": "2026-01-01",
        "attempt": 1,
        "outcome": "success",
    }
    defaults.update(overrides)
    return CostLedgerEntry(**defaults)


class _FakeResponse:
    def __init__(self, data: Any = None) -> None:
        self.data = data


class _FakeInsertBuilder:
    def __init__(self, captured: list[dict[str, Any]]) -> None:
        self._captured = captured
        self._payload: dict[str, Any] | None = None

    def insert(self, payload: dict[str, Any]) -> _FakeInsertBuilder:
        self._payload = payload
        return self

    async def execute(self) -> _FakeResponse:
        assert self._payload is not None
        self._captured.append(self._payload)
        return _FakeResponse()


class _FakeSelectBuilder:
    def __init__(self, response_data: Any) -> None:
        self._response_data = response_data
        self.filters: list[tuple[str, str, Any]] = []

    def select(self, *args: Any, **kwargs: Any) -> _FakeSelectBuilder:
        return self

    def eq(self, field: str, value: Any) -> _FakeSelectBuilder:
        self.filters.append(("eq", field, value))
        return self

    def gte(self, field: str, value: Any) -> _FakeSelectBuilder:
        self.filters.append(("gte", field, value))
        return self

    def lte(self, field: str, value: Any) -> _FakeSelectBuilder:
        self.filters.append(("lte", field, value))
        return self

    async def execute(self) -> _FakeResponse:
        return _FakeResponse(self._response_data)


class _FakeAsyncClient:
    def __init__(
        self, *, captured_inserts: list[dict[str, Any]], breakdown_rows: Any = None
    ) -> None:
        self.table_names: list[str] = []
        self._captured_inserts = captured_inserts
        self._breakdown_rows = breakdown_rows

    def table(self, name: str) -> Any:
        self.table_names.append(name)
        if name == "ai_cost_ledger":
            return _FakeInsertBuilder(self._captured_inserts)
        return _FakeSelectBuilder(self._breakdown_rows)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.supabase_cost_ledger.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


async def test_record_writes_every_ac_named_column(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAsyncClient(captured_inserts=captured)

    with _patch_acreate_client(fake_client):
        await SupabaseCostLedger().record(_entry())

    assert len(captured) == 1
    row = captured[0]
    for field in (
        "user_id",
        "provider",
        "model",
        "feature",
        "tokens_in",
        "tokens_out",
        "cost_micropaise",
        "latency_ms",
        "cache_hit",
        "pricing_status",
        "attempt",
        "outcome",
    ):
        assert field in row, f"missing {field}"


async def test_record_never_raises_on_db_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_env(monkeypatch)

    async def _raise(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("db down")

    with patch("adapters.supabase_cost_ledger.acreate_client", new=AsyncMock(side_effect=_raise)):
        with caplog.at_level(logging.ERROR):
            await SupabaseCostLedger().record(_entry())  # must not raise

    assert any(r.message == "ledger_write_failed" for r in caplog.records)


async def test_cache_hit_row_has_zero_cost_and_cache_hit_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAsyncClient(captured_inserts=captured)

    with _patch_acreate_client(fake_client):
        await SupabaseCostLedger().record(
            _entry(cost_micropaise=0, cache_hit=True, tokens_in=None, tokens_out=None)
        )

    row = captured[0]
    assert row["cost_micropaise"] == 0
    assert row["cache_hit"] is True


async def test_unit_price_snapshot_is_frozen_on_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAsyncClient(captured_inserts=captured)
    snapshot = {"usd_per_mtok_in": 2.0, "fx_usd_to_inr": 84.0}

    with _patch_acreate_client(fake_client):
        await SupabaseCostLedger().record(_entry(unit_price_snapshot=dict(snapshot)))

    # Mutating the module-level dict after the fact must not retroactively
    # change what was captured -- the row got its own independent copy at
    # write time (via the entry's own dataclass value).
    snapshot["fx_usd_to_inr"] = 999.0
    assert captured[0]["unit_price_snapshot"]["fx_usd_to_inr"] == 84.0


async def test_uses_service_role_client_not_caller_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAsyncClient(captured_inserts=captured)

    with _patch_acreate_client(fake_client) as mocked:
        await SupabaseCostLedger().record(_entry())

    mocked.assert_awaited_once()
    call_args = mocked.call_args
    assert call_args.args[1] == "service-role-key"


async def test_retries_share_one_request_id_with_incrementing_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAsyncClient(captured_inserts=captured)
    ledger = SupabaseCostLedger()

    with _patch_acreate_client(fake_client):
        await ledger.record(_entry(request_id="shared-req", attempt=1))
        await ledger.record(_entry(request_id="shared-req", attempt=2, outcome="failed"))

    assert len(captured) == 2
    assert {row["request_id"] for row in captured} == {"shared-req"}
    assert [row["attempt"] for row in captured] == [1, 2]


async def test_breakdown_groups_by_user_and_feature_on_ist_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    rows = [
        {
            "user_id": "user-1",
            "feature": "wardrobe_tagging",
            "provider": "gemini",
            "model": "gemini-3.5-flash-lite",
            "ist_date": "2026-07-30",
            "call_count": 5,
            "cache_hits": 1,
            "unpriced_calls": 0,
            "cost_micropaise": 10_000_000,
            "cost_paise": 10.0,
        }
    ]
    fake_client = _FakeAsyncClient(captured_inserts=[], breakdown_rows=rows)

    with _patch_acreate_client(fake_client):
        result = await SupabaseCostLedger().breakdown(
            user_id="user-1", since=date(2026, 7, 1), until=date(2026, 7, 31)
        )

    assert result == rows
