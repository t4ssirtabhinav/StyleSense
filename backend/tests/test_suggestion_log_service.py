"""Tests for backend/services/suggestion_log_service.py (SS-033). Fake
``ISuggestionLogRepository`` recording calls; no network. Per the design
doc §7.1's own test list -- each test is named against the AC it covers."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from adapters.interfaces import (
    ISuggestionLogRepository,
    SuggestionImpressionLog,
    SuggestionOutcomeLog,
    SuggestionSessionLog,
)
from services.styling_rules_types import RuleScore, ScoredCandidate
from services.suggestion_log_service import (
    ENGINE_VERSION,
    SuggestionLogService,
    config_snapshot_hash,
    impressions_from_candidates,
    outfit_fingerprint,
)


class _FakeRepository(ISuggestionLogRepository):
    def __init__(
        self,
        *,
        session_id: str | None = "session-1",
        raise_on_log_session: Exception | None = None,
    ) -> None:
        self.log_session_calls: list[
            tuple[SuggestionSessionLog, list[SuggestionImpressionLog]]
        ] = []
        self._session_id = session_id
        self._raise = raise_on_log_session

    async def log_session(
        self,
        session: SuggestionSessionLog,
        impressions: Sequence[SuggestionImpressionLog],
    ) -> str | None:
        self.log_session_calls.append((session, list(impressions)))
        if self._raise is not None:
            raise self._raise
        return self._session_id

    async def log_outcome(self, outcome: SuggestionOutcomeLog) -> str | None:
        raise NotImplementedError

    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict[str, Any]]:
        return []

    async def update_session_outcome(
        self, *, session_id: str, cost_incurred: bool, request_id: str | None, latency_ms: int | None
    ) -> None:
        return None

    async def find_impression(self, *, session_id: str, rank: int):  # type: ignore[no-untyped-def]
        return None


def _candidate(item_ids: list[str], score: float = 0.8) -> ScoredCandidate:
    return ScoredCandidate(
        item_ids=item_ids,
        category_labels={item_id: "top" for item_id in item_ids},
        total_score=score,
        rule_scores=[RuleScore(rule="color_harmony", score=score, explanation="matches well")],
        gap_flags=[],
    )


async def test_one_request_produces_exactly_one_session_and_n_impressions() -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)
    candidates = [_candidate(["a", "b"]), _candidate(["c", "d"]), _candidate(["e"])]

    result = await service.log_suggestion(user_id="user-1", candidates=candidates)

    assert result == "session-1"
    assert len(repo.log_session_calls) == 1
    session, impressions = repo.log_session_calls[0]
    assert len(impressions) == len(candidates) == 3
    assert session.candidate_count == 3


async def test_session_carries_occasion_weather_tier_effort_engine_and_config_hash() -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)

    await service.log_suggestion(
        user_id="user-1",
        occasion="office",
        weather_data={"tempC": 28},
        tier="premium",
        effort_tier="E2",
        config_snapshot={"gemini_quota_ceiling_rpm": {"rpm": 15}},
        candidates=[_candidate(["a"])],
    )

    session, _ = repo.log_session_calls[0]
    assert session.occasion == "office"
    assert session.weather_data == {"tempC": 28}
    assert session.tier == "premium"
    assert session.effort_tier == "E2"
    assert session.engine_version == ENGINE_VERSION
    assert session.config_snapshot_hash is not None


async def test_impression_carries_item_ids_total_score_rule_breakdown_rank_and_exploration_flag() -> (
    None
):
    repo = _FakeRepository()
    service = SuggestionLogService(repo)
    candidate = _candidate(["a", "b"], score=0.42)

    await service.log_suggestion(user_id="user-1", candidates=[candidate], exploration_ranks={1})

    _, impressions = repo.log_session_calls[0]
    impression = impressions[0]
    assert impression.item_ids == ["a", "b"]
    assert impression.total_score == 0.42
    assert impression.rule_scores == [
        {"rule": "color_harmony", "score": 0.42, "explanation": "matches well"}
    ]
    assert impression.rank == 1
    assert impression.is_exploration is True


async def test_ranks_are_one_based_and_follow_engine_order() -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)
    candidates = [_candidate(["a"]), _candidate(["b"]), _candidate(["c"])]

    await service.log_suggestion(user_id="user-1", candidates=candidates)

    _, impressions = repo.log_session_calls[0]
    assert [impression.rank for impression in impressions] == [1, 2, 3]
    assert [impression.item_ids for impression in impressions] == [["a"], ["b"], ["c"]]


async def test_exploration_ranks_flag_only_the_named_ranks() -> None:
    candidates = [_candidate(["a"]), _candidate(["b"]), _candidate(["c"])]

    impressions = impressions_from_candidates(candidates, exploration_ranks={2})

    assert [impression.is_exploration for impression in impressions] == [False, True, False]


def test_fingerprint_is_order_independent() -> None:
    a = outfit_fingerprint(["item-1", "item-2", "item-3"])
    b = outfit_fingerprint(["item-3", "item-1", "item-2"])
    c = outfit_fingerprint(["item-2", "item-3", "item-1"])
    assert a == b == c


def test_fingerprint_differs_for_different_item_sets() -> None:
    a = outfit_fingerprint(["item-1", "item-2", "item-3"])
    b = outfit_fingerprint(["item-1", "item-2", "item-4"])
    assert a != b


def test_fingerprint_is_64_char_lowercase_hex() -> None:
    fingerprint = outfit_fingerprint(["item-1", "item-2"])
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)


def test_config_snapshot_hash_is_stable_across_key_order() -> None:
    a = config_snapshot_hash({"x": 1, "y": 2})
    b = config_snapshot_hash({"y": 2, "x": 1})
    assert a == b


def test_config_snapshot_hash_changes_when_a_value_changes() -> None:
    a = config_snapshot_hash({"x": 1})
    b = config_snapshot_hash({"x": 2})
    assert a != b


async def test_cache_hit_marks_cost_not_incurred_with_reason() -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)

    await service.log_suggestion(
        user_id="user-1",
        candidates=[_candidate(["a"])],
        cost_incurred=False,
        zero_cost_reason="cache_hit",
    )

    session, _ = repo.log_session_calls[0]
    assert session.cost_incurred is False
    assert session.zero_cost_reason == "cache_hit"


async def test_degraded_e0_marks_cost_not_incurred_and_still_logs_impressions() -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)
    candidates = [_candidate(["a"]), _candidate(["b"])]

    result = await service.log_suggestion(
        user_id="user-1",
        candidates=candidates,
        effort_tier="E0",
        cost_incurred=False,
        zero_cost_reason="degraded_e0",
    )

    assert result == "session-1"
    session, impressions = repo.log_session_calls[0]
    assert session.effort_tier == "E0"
    assert session.cost_incurred is False
    assert len(impressions) == 2


async def test_repository_raise_does_not_break_the_caller(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = _FakeRepository(raise_on_log_session=RuntimeError("db exploded"))
    service = SuggestionLogService(repo)

    with caplog.at_level(logging.ERROR):
        result = await service.log_suggestion(user_id="user-1", candidates=[_candidate(["a"])])

    assert result is None
    assert "suggestion_log_failed" in caplog.text


async def test_malformed_candidate_does_not_propagate(caplog: pytest.LogCaptureFixture) -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)
    # A candidate missing rule_scores entirely (not a real ScoredCandidate)
    # -- exercises the service's own defensive wrapping, not the DB.
    malformed = SimpleNamespace(item_ids=["a"], total_score=0.5, gap_flags=[])

    with caplog.at_level(logging.ERROR):
        result = await service.log_suggestion(user_id="user-1", candidates=[malformed])  # type: ignore[list-item]

    assert result is None
    assert "suggestion_log_failed" in caplog.text
    assert repo.log_session_calls == []


def test_engine_version_constant_is_non_empty_and_versioned() -> None:
    assert re.fullmatch(r"[a-z0-9_]+-v\d+", ENGINE_VERSION)


async def test_zero_cost_reason_required_when_cost_not_incurred(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = _FakeRepository()
    service = SuggestionLogService(repo)

    with caplog.at_level(logging.ERROR):
        result = await service.log_suggestion(
            user_id="user-1", candidates=[_candidate(["a"])], cost_incurred=False
        )

    assert result is None
    assert repo.log_session_calls == []
    assert "suggestion_log_zero_cost_reason_missing" in caplog.text


async def test_zero_cost_reason_rejected_when_cost_is_incurred(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The mirror case of the CHECK constraint's other branch: a
    zero_cost_reason on a cost_incurred=True row is just as contradictory."""
    repo = _FakeRepository()
    service = SuggestionLogService(repo)

    with caplog.at_level(logging.ERROR):
        result = await service.log_suggestion(
            user_id="user-1",
            candidates=[_candidate(["a"])],
            cost_incurred=True,
            zero_cost_reason="cache_hit",
        )

    assert result is None
    assert repo.log_session_calls == []
    assert "suggestion_log_zero_cost_reason_unexpected" in caplog.text
