"""Tests for the SS-023 `exclude_fingerprints` regenerate mechanism, at
`engine_v2_portfolio.select_portfolio`'s level (design §4, test plan
`test_engine_v2_exclusion.py`)."""

from __future__ import annotations

from services.engine_v2_portfolio import compute_outfit_fingerprint, select_portfolio
from services.styling_rules_types import GapReport, RuleScore, ScoredCandidate

_EMPTY_GAP_REPORT = GapReport()


def _candidate(item_ids: list[str], score: float) -> ScoredCandidate:
    return ScoredCandidate(
        item_ids=item_ids,
        category_labels={},
        total_score=score,
        rule_scores=[RuleScore(rule="formality_fit", score=score, explanation="x")],
        gap_flags=[],
    )


def test_excluded_candidate_never_appears_in_portfolio() -> None:
    excluded = _candidate(["a", "b"], 0.95)
    others = [_candidate([f"x{i}", f"y{i}"], 0.9 - i * 0.01) for i in range(6)]
    scored = [excluded] + others
    exclude_fp = frozenset({compute_outfit_fingerprint(excluded.item_ids)})

    result = select_portfolio(
        scored,
        score_floor=0.5,
        lambda_=0.75,
        gap_report=_EMPTY_GAP_REPORT,
        exclude_fingerprints=exclude_fp,
    )
    selected_ids = {tuple(pc.candidate.item_ids) for pc in result.portfolio}
    assert tuple(excluded.item_ids) not in selected_ids


def test_exclusion_happens_before_mmr_not_after() -> None:
    """With the top-scoring candidate excluded, the returned set is the
    best REMAINING diverse set, not the original set minus one -- proven by
    the top-scored survivor now anchoring the MMR seed."""
    top = _candidate(["top1", "top2"], 0.99)
    second = _candidate(["second1", "second2"], 0.95)
    third = _candidate(["third1", "third2"], 0.90)
    scored = [top, second, third]
    exclude_fp = frozenset({compute_outfit_fingerprint(top.item_ids)})

    result = select_portfolio(
        scored,
        score_floor=0.5,
        lambda_=0.75,
        gap_report=_EMPTY_GAP_REPORT,
        exclude_fingerprints=exclude_fp,
    )
    main = [pc for pc in result.portfolio if not pc.is_exploration]
    # The seed (first-selected) is now the best REMAINING candidate, `second`.
    assert tuple(main[0].candidate.item_ids) == tuple(second.item_ids)
    selected_ids = {tuple(pc.candidate.item_ids) for pc in result.portfolio}
    assert tuple(top.item_ids) not in selected_ids


def test_excluding_everything_returns_empty_portfolio_limited_options_true_no_exception() -> None:
    scored = [_candidate([f"a{i}", f"b{i}"], 0.9) for i in range(5)]
    exclude_fp = frozenset(compute_outfit_fingerprint(c.item_ids) for c in scored)

    result = select_portfolio(
        scored,
        score_floor=0.5,
        lambda_=0.75,
        gap_report=_EMPTY_GAP_REPORT,
        exclude_fingerprints=exclude_fp,
    )
    assert result.portfolio == []
    assert result.limited_options is True


def test_exclude_fingerprints_none_reproduces_pre_ss023_output_byte_for_byte() -> None:
    """Additive-widening proof: a fixed fixture, same result whether the
    new kwarg is omitted or explicitly None."""
    scored = [_candidate([f"a{i}", f"b{i}"], 0.9 - (i % 3) * 0.05) for i in range(15)]

    baseline = select_portfolio(scored, score_floor=0.5, lambda_=0.75, gap_report=_EMPTY_GAP_REPORT)
    with_none = select_portfolio(
        scored,
        score_floor=0.5,
        lambda_=0.75,
        gap_report=_EMPTY_GAP_REPORT,
        exclude_fingerprints=None,
    )
    with_empty = select_portfolio(
        scored,
        score_floor=0.5,
        lambda_=0.75,
        gap_report=_EMPTY_GAP_REPORT,
        exclude_fingerprints=frozenset(),
    )

    baseline_ids = [tuple(pc.candidate.item_ids) for pc in baseline.portfolio]
    none_ids = [tuple(pc.candidate.item_ids) for pc in with_none.portfolio]
    empty_ids = [tuple(pc.candidate.item_ids) for pc in with_empty.portfolio]
    assert baseline_ids == none_ids == empty_ids
    assert baseline.limited_options == with_none.limited_options == with_empty.limited_options
