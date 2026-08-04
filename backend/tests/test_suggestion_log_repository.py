"""Tests for backend/adapters/suggestion_log_repository.py (SS-033), mocked
``supabase-py`` async client -- no real network/DB calls.

Mirrors test_app_config_repository.py's fake-``AsyncClient``-builder style
(the ``service_role``-uses-it-deliberately inverted assertion), extended to
support ``.insert()`` and the read-side filter chain
(``.select().eq().gte().order().limit()``) that ``recent_impressions()``
needs. Per the design doc §7.2's own test list.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.interfaces import SuggestionImpressionLog, SuggestionOutcomeLog, SuggestionSessionLog
from adapters.suggestion_log_repository import SupabaseSuggestionLogRepository


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    def __init__(self, table_name: str, client: _FakeAsyncClient) -> None:
        self.table_name = table_name
        self._client = client
        self._filters: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def insert(self, payload: Any) -> _FakeQueryBuilder:
        self._client.insert_calls.append((self.table_name, payload))
        return self

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._filters.append(("select", args, kwargs))
        return self

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._filters.append(("eq", args, kwargs))
        return self

    def gte(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._filters.append(("gte", args, kwargs))
        return self

    def order(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._filters.append(("order", args, kwargs))
        return self

    def limit(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._filters.append(("limit", args, kwargs))
        return self

    async def execute(self) -> _FakeResponse:
        self._client.execute_calls.append(self.table_name)
        if self.table_name in self._client.errors:
            raise self._client.errors[self.table_name]
        return _FakeResponse(self._client.responses.get(self.table_name, []))


class _FakeAsyncClient:
    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.errors = errors or {}
        self.insert_calls: list[tuple[str, Any]] = []
        self.execute_calls: list[str] = []
        self.table_calls: list[str] = []

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_calls.append(name)
        return _FakeQueryBuilder(name, self)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.suggestion_log_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


def _session() -> SuggestionSessionLog:
    return SuggestionSessionLog(user_id="user-1", occasion="office", candidate_count=2)


def _impressions(n: int = 8) -> list[SuggestionImpressionLog]:
    return [
        SuggestionImpressionLog(
            rank=i,
            item_ids=[f"item-{i}"],
            outfit_fingerprint="a" * 64,
            total_score=0.5,
        )
        for i in range(1, n + 1)
    ]


async def test_uses_service_role_key_not_anon_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(responses={"suggestion_sessions": [{"id": "session-1"}]})

    with _patch_acreate_client(fake_client) as mocked:
        await SupabaseSuggestionLogRepository().log_session(_session(), [])

    mocked.assert_awaited()
    for call in mocked.call_args_list:
        assert call.args[1] == "service-role-key"
        assert "anon-key" not in call.args


async def test_session_insert_then_batched_impression_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(responses={"suggestion_sessions": [{"id": "session-1"}]})

    with _patch_acreate_client(fake_client):
        await SupabaseSuggestionLogRepository().log_session(_session(), _impressions(8))

    # Exactly two PostgREST calls for 8 impressions, not nine: one session
    # insert, one BATCHED impression insert.
    assert fake_client.execute_calls == ["suggestion_sessions", "suggestion_impressions"]
    assert len(fake_client.insert_calls) == 2
    impression_table, impression_payload = fake_client.insert_calls[1]
    assert impression_table == "suggestion_impressions"
    assert isinstance(impression_payload, list)
    assert len(impression_payload) == 8


async def test_impressions_carry_the_returned_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(responses={"suggestion_sessions": [{"id": "session-xyz"}]})

    with _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().log_session(_session(), _impressions(3))

    assert result == "session-xyz"
    _, impression_payload = fake_client.insert_calls[1]
    assert all(row["session_id"] == "session-xyz" for row in impression_payload)


async def test_session_insert_failure_returns_none_and_writes_no_impressions(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(errors={"suggestion_sessions": RuntimeError("db down")})

    with caplog.at_level(logging.ERROR), _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().log_session(_session(), _impressions(3))

    assert result is None
    # The session insert was attempted (and failed); no impression insert
    # was attempted as a result.
    assert [table for table, _ in fake_client.insert_calls] == ["suggestion_sessions"]
    assert "suggestion_session_log_failed" in caplog.text


async def test_impression_insert_failure_still_returns_the_session_id(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(
        responses={"suggestion_sessions": [{"id": "session-1"}]},
        errors={"suggestion_impressions": RuntimeError("insert failed")},
    )

    with caplog.at_level(logging.ERROR), _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().log_session(_session(), _impressions(3))

    # Session row is real -- not rolled back or deleted just because the
    # impressions failed (design §5.2 item 4).
    assert result == "session-1"
    assert "suggestion_impression_log_failed" in caplog.text


async def test_log_session_never_raises_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(errors={"suggestion_sessions": ValueError("weird failure")})

    with _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().log_session(_session(), _impressions(2))

    assert result is None


async def test_log_outcome_never_raises_and_returns_none_on_dedupe_conflict(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(
        errors={
            "suggestion_outcomes": RuntimeError(
                'duplicate key value violates unique constraint "uq_suggestion_outcomes_dedupe"'
            )
        }
    )
    outcome = SuggestionOutcomeLog(
        impression_id="impression-1", outcome_type="saved", dedupe_key="retry-1"
    )

    with caplog.at_level(logging.INFO), _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().log_outcome(outcome)

    assert result is None
    assert "suggestion_outcome_dedupe_conflict" in caplog.text


async def test_recent_impressions_returns_empty_list_on_db_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(errors={"suggestion_impressions": RuntimeError("timeout")})

    with _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().recent_impressions(
            user_id="user-1", since=datetime.now(UTC) - timedelta(days=1)
        )

    assert result == []


async def test_future_client_occurred_at_is_clamped_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(responses={"suggestion_outcomes": [{"id": "outcome-1"}]})
    far_future = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    outcome = SuggestionOutcomeLog(
        impression_id="impression-1", outcome_type="saved", client_occurred_at=far_future
    )

    with caplog.at_level(logging.WARNING), _patch_acreate_client(fake_client):
        result = await SupabaseSuggestionLogRepository().log_outcome(outcome)

    assert result == "outcome-1"
    assert "suggestion_outcome_clock_skew" in caplog.text
    _, payload = fake_client.insert_calls[0]
    clamped = datetime.fromisoformat(payload["client_occurred_at"])
    assert clamped - datetime.now(UTC) < timedelta(minutes=1)


async def test_outcome_row_includes_every_ac_named_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake_client = _FakeAsyncClient(responses={"suggestion_outcomes": [{"id": "outcome-1"}]})
    outcome = SuggestionOutcomeLog(
        impression_id="impression-1",
        outcome_type="worn",
        outfit_id="outfit-1",
        dedupe_key="dedupe-1",
        client_occurred_at=datetime.now(UTC).isoformat(),
        metadata={"source": "wardrobe"},
    )

    with _patch_acreate_client(fake_client):
        await SupabaseSuggestionLogRepository().log_outcome(outcome)

    _, payload = fake_client.insert_calls[0]
    assert payload["impression_id"] == "impression-1"
    assert payload["outcome_type"] == "worn"
    assert payload["outfit_id"] == "outfit-1"
    assert payload["dedupe_key"] == "dedupe-1"
    assert payload["client_occurred_at"] is not None
    assert payload["metadata"] == {"source": "wardrobe"}
    # No user_id sent -- the trigger derives it from the impression's owner
    # (design §3.5); SuggestionOutcomeLog carries no such field at all.
    assert "user_id" not in payload
