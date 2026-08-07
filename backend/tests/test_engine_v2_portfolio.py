"""Tests for backend/services/engine_v2_portfolio.py (SS-038)."""

from __future__ import annotations

import re

from services.engine_v2_portfolio import (
    compute_outfit_fingerprint,
    jaccard_similarity,
    select_portfolio,
)
from services.styling_rules_types import GapReport, RuleScore, ScoredCandidate

_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_EMPTY_GAP_REPORT = GapReport()


def _candidate(item_ids: list[str], score: float) -> ScoredCandidate:
    return ScoredCandidate(
        item_ids=item_ids,
        category_labels={},
        total_score=score,
        rule_scores=[RuleScore(rule="formality_fit", score=score, explanation="x")],
        gap_flags=[],
    )


# ---------------------------------------------------------------------------
# compute_outfit_fingerprint
# ---------------------------------------------------------------------------


def test_compute_outfit_fingerprint_order_independent() -> None:
    fp1 = compute_outfit_fingerprint(["a", "b"])
    fp2 = compute_outfit_fingerprint(["b", "a"])
    assert fp1 == fp2


def test_compute_outfit_fingerprint_matches_db_check_shape() -> None:
    fp = compute_outfit_fingerprint(["item1", "item2", "item3"])
    assert _FINGERPRINT_RE.match(fp)


def test_compute_outfit_fingerprint_different_sets_differ() -> None:
    assert compute_outfit_fingerprint(["a", "b"]) != compute_outfit_fingerprint(["a", "c"])


# ---------------------------------------------------------------------------
# jaccard_similarity
# ---------------------------------------------------------------------------


def test_jaccard_similarity_identical_sets_is_1() -> None:
    a = _candidate(["x", "y"], 0.8)
    b = _candidate(["x", "y"], 0.7)
    assert jaccard_similarity(a, b) == 1.0


def test_jaccard_similarity_disjoint_sets_is_0() -> None:
    a = _candidate(["x", "y"], 0.8)
    b = _candidate(["p", "q"], 0.7)
    assert jaccard_similarity(a, b) == 0.0


def test_jaccard_similarity_partial_overlap() -> None:
    a = _candidate(["x", "y", "z"], 0.8)
    b = _candidate(["x", "y", "w"], 0.7)
    # intersection {x,y}=2, union {x,y,z,w}=4
    assert jaccard_similarity(a, b) == 0.5


# ---------------------------------------------------------------------------
# select_portfolio
# ---------------------------------------------------------------------------


def test_never_includes_below_floor_candidate_even_if_most_diverse() -> None:
    """Constructs a pool where the highest-diversity candidate is
    deliberately below-floor and asserts it's excluded from both the main
    portfolio and the exploration slots."""
    above_floor = [_candidate([f"common{i}", f"common{i+1}"], 0.9) for i in range(6)]
    below_floor_diverse = _candidate(["totally", "different", "items"], 0.1)
    scored = above_floor + [below_floor_diverse]

    result = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    all_ids = {tuple(pc.candidate.item_ids) for pc in result.portfolio}
    assert tuple(below_floor_diverse.item_ids) not in all_ids
    for pc in result.portfolio:
        assert pc.candidate.total_score >= 0.5


def test_returns_5_to_8_when_pool_is_large() -> None:
    scored = [_candidate([f"a{i}", f"b{i}"], 0.9 - i * 0.01) for i in range(20)]
    result = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    main_portfolio = [pc for pc in result.portfolio if not pc.is_exploration]
    assert 5 <= len(main_portfolio) <= 8


def test_honest_smaller_count_when_pool_between_3_and_4() -> None:
    scored = [_candidate([f"a{i}", f"b{i}"], 0.9) for i in range(4)]
    result = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    main_portfolio = [pc for pc in result.portfolio if not pc.is_exploration]
    assert len(main_portfolio) == 4  # honest, not padded
    assert result.limited_options is False  # 4 >= 3


def test_limited_options_true_when_eligible_pool_under_3() -> None:
    scored = [_candidate(["a", "b"], 0.9), _candidate(["c", "d"], 0.8)]
    result = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    assert result.limited_options is True


def test_empty_scored_pool_returns_empty_portfolio_no_crash() -> None:
    result = select_portfolio([], score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    assert result.portfolio == []
    assert result.limited_options is True


def test_deterministic_across_repeated_calls() -> None:
    scored = [_candidate([f"a{i}", f"b{i}"], 0.9 - (i % 3) * 0.05) for i in range(15)]
    result1 = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    result2 = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    ids1 = [tuple(pc.candidate.item_ids) for pc in result1.portfolio]
    ids2 = [tuple(pc.candidate.item_ids) for pc in result2.portfolio]
    assert ids1 == ids2


def test_exploration_candidates_flagged_and_never_below_floor() -> None:
    scored = [_candidate([f"a{i}", f"b{i}"], 0.9 - i * 0.02) for i in range(15)]
    result = select_portfolio(
        scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT, max_exploration=2
    )
    exploration = [pc for pc in result.portfolio if pc.is_exploration]
    assert len(exploration) <= 2
    for pc in exploration:
        assert pc.candidate.total_score >= 0.5


def test_gap_report_passed_through() -> None:
    gap_report = GapReport(excluded_missing_color_or_category=3, missing_slots=["footwear"])
    result = select_portfolio(
        [_candidate(["a", "b"], 0.9)], score_floor=0.5, lambda_=0.75, gap_report=gap_report
    )
    assert result.gap_report == gap_report


def test_mmr_diversity_reorders_above_floor() -> None:
    """Two near-identical high-score candidates and one lower-score but
    diverse one -- MMR should prefer diversity over a marginal score gain
    once several already-selected candidates cover the common items."""
    common_a = _candidate(["shared1", "shared2"], 0.95)
    common_b = _candidate(["shared1", "shared3"], 0.94)
    common_c = _candidate(["shared1", "shared4"], 0.93)
    diverse = _candidate(["unique1", "unique2"], 0.80)

    scored = [common_a, common_b, common_c, diverse]
    result = select_portfolio(scored, score_floor=0.5, lambda_=0.5, gap_report=_EMPTY_GAP_REPORT)
    selected_ids = [tuple(pc.candidate.item_ids) for pc in result.portfolio]
    assert tuple(diverse.item_ids) in selected_ids
