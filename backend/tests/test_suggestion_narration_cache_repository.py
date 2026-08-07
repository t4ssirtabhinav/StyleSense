"""Tests for backend/adapters/suggestion_narration_cache_repository.py
(SS-020), mocked ``supabase-py`` async client -- no real network/DB calls.

Mirrors test_app_config_repository.py's style: ``service_role``, never
anon+JWT (this table has no per-user ownership at all)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.suggestion_narration_cache_repository import (
    SupabaseSuggestionNarrationCacheRepository,
)


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(self, calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]], response_data: Any) -> None:
        self._calls = calls
        self._response_data = response_data

    def _record(self, name: str, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._calls.append((name, args, kwargs))
        return self

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("select", *args, **kwargs)

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("eq", *args, **kwargs)

    def limit(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("limit", *args, **kwargs)

    def update(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("update", *args, **kwargs)

    def upsert(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("upsert", *args, **kwargs)

    async def execute(self) -> _FakeResponse:
        self._calls.append(("execute", (), {}))
        return _FakeResponse(self._response_data)


class _FakeAsyncClient:
    def __init__(self, response_data: Any = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.table_names: list[str] = []
        self._response_data = response_data

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_names.append(name)
        return _FakeQueryBuilder(self.calls, self._response_data)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.suggestion_narration_cache_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


class _RaisingAcreateClient:
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("connection refused")


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


async def test_get_uses_service_role_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient([])
    repo = SupabaseSuggestionNarrationCacheRepository()

    with _patch_acreate_client(fake_client) as mocked:
        await repo.get(signature_hash="a" * 64)

    mocked.assert_awaited_once_with("https://example.supabase.co", "service-role-key")


async def test_get_cache_miss_returns_none() -> None:
    repo = SupabaseSuggestionNarrationCacheRepository()
    with patch(
        "adapters.suggestion_narration_cache_repository.acreate_client",
        new=AsyncMock(return_value=_FakeAsyncClient([])),
    ), patch.dict("os.environ", {"SUPABASE_URL": "u", "SUPABASE_SERVICE_ROLE_KEY": "k"}):
        result = await repo.get(signature_hash="a" * 64)
    assert result is None


async def test_get_cache_hit_returns_cached_narration() -> None:
    row = {
        "narrations": {"0": "a great pick", "1": "another good one"},
        "language": "en",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "hit_count": 3,
    }
    repo = SupabaseSuggestionNarrationCacheRepository()
    with patch(
        "adapters.suggestion_narration_cache_repository.acreate_client",
        new=AsyncMock(return_value=_FakeAsyncClient([row])),
    ), patch.dict("os.environ", {"SUPABASE_URL": "u", "SUPABASE_SERVICE_ROLE_KEY": "k"}):
        result = await repo.get(signature_hash="a" * 64)

    assert result is not None
    assert result.narrations_by_signature_index == {0: "a great pick", 1: "another good one"}
    assert result.language == "en"


async def test_get_expired_row_treated_as_miss() -> None:
    row = {
        "narrations": {"0": "stale narration"},
        "language": "en",
        "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "hit_count": 0,
    }
    repo = SupabaseSuggestionNarrationCacheRepository()
    with patch(
        "adapters.suggestion_narration_cache_repository.acreate_client",
        new=AsyncMock(return_value=_FakeAsyncClient([row])),
    ), patch.dict("os.environ", {"SUPABASE_URL": "u", "SUPABASE_SERVICE_ROLE_KEY": "k"}):
        result = await repo.get(signature_hash="a" * 64)
    assert result is None


async def test_get_never_raises_on_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    repo = SupabaseSuggestionNarrationCacheRepository()
    with patch(
        "adapters.suggestion_narration_cache_repository.acreate_client",
        new=_RaisingAcreateClient(),
    ):
        result = await repo.get(signature_hash="a" * 64)  # must not raise
    assert result is None


async def test_put_never_raises_on_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    repo = SupabaseSuggestionNarrationCacheRepository()
    with patch(
        "adapters.suggestion_narration_cache_repository.acreate_client",
        new=_RaisingAcreateClient(),
    ):
        await repo.put(
            signature_hash="a" * 64,
            occasion_key="office",
            engine_version="engine-v2",
            narrations_by_signature_index={0: "text"},
            language="en",
            ttl_seconds=21600,
        )  # must not raise


async def test_put_upserts_with_signature_hash_as_the_conflict_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient([])
    repo = SupabaseSuggestionNarrationCacheRepository()

    with _patch_acreate_client(fake_client):
        await repo.put(
            signature_hash="a" * 64,
            occasion_key="office",
            engine_version="engine-v2",
            narrations_by_signature_index={0: "text"},
            language="en",
            ttl_seconds=21600,
        )

    upsert_calls = [c for c in fake_client.calls if c[0] == "upsert"]
    assert len(upsert_calls) == 1
    payload = upsert_calls[0][1][0]
    assert payload["signature_hash"] == "a" * 64
    assert payload["narrations"] == {"0": "text"}
    assert upsert_calls[0][2]["on_conflict"] == "signature_hash"
