"""Tests for backend/services/engine_v2_novelty.py (SS-038)."""

from __future__ import annotations

from datetime import date, datetime

from adapters.interfaces import ISuggestionLogRepository, IWearHistoryRepository, WearRecency
from services.engine_v2_novelty import compute_novelty_score, fetch_novelty_inputs
from services.engine_v2_types import NoveltyInputs

_AS_OF = date(2026, 7, 29)


class _FakeWearHistoryRepo(IWearHistoryRepository):
    """``internal_failure=True`` simulates a REAL implementation's own
    internal try/except catching a DB error and degrading to ``[]`` -- per
    the port's own never-raise contract, this fake never propagates,
    exactly like ``SupabaseWearHistoryRepository`` doesn't."""

    def __init__(self, rows: list[WearRecency] | None = None, *, internal_failure: bool = False) -> None:
        self._rows = rows or []
        self._internal_failure = internal_failure

    async def fetch_wear_recency(
        self, *, jwt: str, user_id: str, occasion_key: str | None = None
    ) -> list[WearRecency]:
        if self._internal_failure:
            return []  # degrades, per the port contract -- never raises
        return self._rows


class _FakeSuggestionLogRepo(ISuggestionLogRepository):
    def __init__(self, impressions: list[dict] | None = None, *, internal_failure: bool = False) -> None:
        self._impressions = impressions or []
        self._internal_failure = internal_failure

    async def log_session(self, session, impressions):  # type: ignore[no-untyped-def]
        return None

    async def log_outcome(self, outcome):  # type: ignore[no-untyped-def]
        return None

    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict]:
        if self._internal_failure:
            return []  # degrades, per the port contract -- never raises
        return self._impressions

    async def update_session_outcome(
        self, *, session_id: str, cost_incurred: bool, request_id: str | None, latency_ms: int | None
    ) -> None:
        return None

    async def find_impression(self, *, session_id: str, rank: int):  # type: ignore[no-untyped-def]
        return None


# ---------------------------------------------------------------------------
# compute_novelty_score
# ---------------------------------------------------------------------------


def test_item_absent_from_inputs_entirely_is_maximally_novel() -> None:
    inputs = NoveltyInputs()
    score = compute_novelty_score(["item1"], "wedding_guest", inputs, as_of=_AS_OF)
    assert score == 1.0


def test_occasion_key_none_degrades_to_days_since_any_not_forced_1() -> None:
    wear_recency = WearRecency(
        item_id="item1",
        last_worn_on=date(2026, 7, 20),  # 9 days ago
        last_worn_on_for_occasion=None,
        wears_for_occasion=0,
    )
    inputs = NoveltyInputs(wear_recency_by_item={"item1": wear_recency})

    score_with_occasion = compute_novelty_score(["item1"], "wedding_guest", inputs, as_of=_AS_OF)
    score_without_occasion = compute_novelty_score(["item1"], None, inputs, as_of=_AS_OF)

    # With a real occasion_key, last_worn_on_for_occasion=None -> days_since_occasion
    # saturates to 1.0 (never worn for THIS occasion) -- maximal novelty on that term.
    # Without an occasion_key (BL-121's Mark Worn case), the occasion term
    # degrades to days_since_any's real (non-maximal) value instead.
    assert score_without_occasion < score_with_occasion


def test_times_shown_reduces_score_monotonically() -> None:
    inputs_low = NoveltyInputs(recent_impression_item_counts={"item1": 0})
    inputs_high = NoveltyInputs(recent_impression_item_counts={"item1": 5})

    score_low = compute_novelty_score(["item1"], "office", inputs_low, as_of=_AS_OF)
    score_high = compute_novelty_score(["item1"], "office", inputs_high, as_of=_AS_OF)
    assert score_high < score_low


def test_candidate_level_score_is_mean_over_items() -> None:
    inputs = NoveltyInputs(recent_impression_item_counts={"item1": 5, "item2": 0})
    single_high = compute_novelty_score(["item1"], "office", inputs, as_of=_AS_OF)
    single_low = compute_novelty_score(["item2"], "office", inputs, as_of=_AS_OF)
    combined = compute_novelty_score(["item1", "item2"], "office", inputs, as_of=_AS_OF)
    assert abs(combined - (single_high + single_low) / 2) < 1e-9


def test_recent_wear_scores_lower_than_never_worn() -> None:
    recent = WearRecency(
        item_id="recent_item",
        last_worn_on=date(2026, 7, 28),  # yesterday
        last_worn_on_for_occasion=date(2026, 7, 28),
        wears_for_occasion=1,
    )
    inputs = NoveltyInputs(wear_recency_by_item={"recent_item": recent})
    recent_score = compute_novelty_score(["recent_item"], "office", inputs, as_of=_AS_OF)
    never_worn_score = compute_novelty_score(["never_worn_item"], "office", inputs, as_of=_AS_OF)
    assert recent_score < never_worn_score


# ---------------------------------------------------------------------------
# fetch_novelty_inputs
# ---------------------------------------------------------------------------


async def test_fetch_novelty_inputs_builds_wear_recency_map() -> None:
    rows = [
        WearRecency(
            item_id="item1", last_worn_on=date(2026, 7, 1), last_worn_on_for_occasion=None, wears_for_occasion=0
        )
    ]
    wear_repo = _FakeWearHistoryRepo(rows)
    log_repo = _FakeSuggestionLogRepo([])

    result = await fetch_novelty_inputs(
        wear_repo, log_repo, jwt="fake-jwt", user_id="u1", occasion_key="office", as_of=_AS_OF
    )
    assert "item1" in result.wear_recency_by_item
    assert result.wear_recency_by_item["item1"].last_worn_on == date(2026, 7, 1)


async def test_fetch_novelty_inputs_counts_impressions_across_all_occasions() -> None:
    """recent_impressions() is NOT occasion-filtered by its own port --
    recent_impression_item_counts must count impressions from EVERY
    occasion, not just the requested one."""
    impressions = [
        {"item_ids": ["item1", "item2"]},
        {"item_ids": ["item1"]},
    ]
    wear_repo = _FakeWearHistoryRepo([])
    log_repo = _FakeSuggestionLogRepo(impressions)

    result = await fetch_novelty_inputs(
        wear_repo, log_repo, jwt="fake-jwt", user_id="u1", occasion_key="office", as_of=_AS_OF
    )
    assert result.recent_impression_item_counts["item1"] == 2
    assert result.recent_impression_item_counts["item2"] == 1


async def test_fetch_novelty_inputs_degrades_to_neutral_on_internal_repo_failure() -> None:
    """DB error degrades to neutral -- proven using the ports' own
    never-raise contract: both fake repos simulate a REAL implementation's
    internal try/except catching a DB error and returning ``[]`` (exactly
    like ``SupabaseWearHistoryRepository``/``SupabaseSuggestionLogRepository``
    do), never propagating. ``fetch_novelty_inputs`` still returns a
    well-formed, empty-but-valid ``NoveltyInputs``."""
    wear_repo = _FakeWearHistoryRepo(internal_failure=True)
    log_repo = _FakeSuggestionLogRepo(internal_failure=True)

    result = await fetch_novelty_inputs(
        wear_repo, log_repo, jwt="fake-jwt", user_id="u1", occasion_key="office", as_of=_AS_OF
    )
    assert result == NoveltyInputs()
    # And the pure scorer still returns a neutral score for any item, from
    # this all-empty NoveltyInputs -- the end-to-end "DB error -> neutral,
    # never a failed suggestion" guarantee.
    assert compute_novelty_score(["any_item"], "office", result, as_of=_AS_OF) == 1.0
