"""SS-038 -- Engine v2 stage ④ (portfolio select), pure.

Maximal Marginal Relevance (``lambda_ * score - (1 - lambda_) * max_similarity_to_
already_selected``) with a hard score floor, returning 5-8 outfits plus 0-2
explicitly-labelled exploration candidates -- diversity only reorders
*above* the floor, never surfaces a below-floor candidate (the floor filter
happens once, before ANY selection, so this is true by construction, not by
a second check).

``jaccard_similarity`` is the Architect's concrete choice for the proposal's
abstract "similarity" term -- flagged as unvalidated, same class as
``ENGINE_V2_RULE_WEIGHTS``, folds into ``BL-077``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from services.engine_v2_types import PortfolioCandidate
from services.styling_rules_defaults import (
    DEFAULT_MAX_EXPLORATION,
    DEFAULT_MMR_LAMBDA,
    DEFAULT_PORTFOLIO_SIZE_RANGE,
    DEFAULT_SCORE_FLOOR,
)
from services.styling_rules_types import GapReport, ScoredCandidate

__all__ = [
    "compute_outfit_fingerprint",
    "jaccard_similarity",
    "PortfolioResult",
    "select_portfolio",
]


@dataclass(frozen=True)
class PortfolioResult:
    portfolio: list[PortfolioCandidate]
    limited_options: bool
    gap_report: GapReport


def compute_outfit_fingerprint(item_ids: list[str]) -> str:
    """Order-independent -- matches ``suggestion_impressions.outfit_fingerprint``'s
    ``^[0-9a-f]{64}$`` CHECK. NOTE: this is a DIFFERENT (comma-joined) hash
    than ``suggestion_log_service.outfit_fingerprint`` (colon-joined,
    SS-033) -- the design doc assigns this exact formula to this module;
    the two functions are not interchangeable for the same item set. Since
    neither has a live caller today (this ticket is the first real writer
    of ``suggestion_impressions``, and does so via this function, not
    ``suggestion_log_service``), there is no live data-compatibility break
    -- flagged as a backlog-worthy consolidation opportunity, not fixed
    here (see worklog)."""
    return hashlib.sha256(",".join(sorted(item_ids)).encode()).hexdigest()


def jaccard_similarity(a: ScoredCandidate, b: ScoredCandidate) -> float:
    set_a = set(a.item_ids)
    set_b = set(b.item_ids)
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def select_portfolio(
    scored: list[ScoredCandidate],
    *,
    score_floor: float = DEFAULT_SCORE_FLOOR,
    lambda_: float = DEFAULT_MMR_LAMBDA,
    gap_report: GapReport,
    portfolio_size_range: tuple[int, int] = DEFAULT_PORTFOLIO_SIZE_RANGE,
    max_exploration: int = DEFAULT_MAX_EXPLORATION,
    exclude_fingerprints: frozenset[str] | None = None,
) -> PortfolioResult:
    """Doc-internal gap-fill, flagged explicitly: the design doc's own
    listed signature for ``select_portfolio`` takes no ``gap_report``
    parameter, yet its own ``PortfolioResult`` shape one line above
    literally includes a ``gap_report: GapReport`` field with no other
    stated source for it. Added ``gap_report`` as a required keyword
    parameter (the orchestrator already holds ``eligibility.excluded_missing_color_or_category``
    and ``search_result.missing_slots`` in scope right before this call) --
    the minimal way to satisfy the doc's own return shape.

    1. ``eligible = [c for c in scored if c.total_score >= score_floor AND
       compute_outfit_fingerprint(c.item_ids) not in exclude_fingerprints]``,
       sorted ``(-total_score, item_ids tuple)`` for determinism. (SS-023)
       ``exclude_fingerprints`` is applied in the SAME filter pass, i.e.
       strictly before MMR selection runs -- so diversity is computed over
       what actually remains, not over a set that then gets holes punched
       in it (design §4). ``None``/empty reproduces pre-SS-023 behaviour
       byte-for-byte (additive-widening pattern, same as SS-020's).
    2. ``limited_options = len(eligible) < 3`` (same threshold semantics as
       v0's ``len(scored) < 3`` -- now naturally also true when exclusion
       leaves too few candidates).
    3. Greedy MMR: seed with the top-scored candidate; repeatedly pick
       ``argmax(lambda_*score - (1-lambda_)*max(jaccard_similarity(c, s) for
       s in selected))`` over remaining eligible candidates, deterministic
       tiebreak ``(-mmr_score, item_ids tuple)``, until
       ``portfolio_size_range[1]`` is reached or ``eligible`` is exhausted.
    4. If the main portfolio ends up smaller than ``portfolio_size_range[0]``,
       that's honest -- return what's available, never fabricate.
    5. Exploration: continue the SAME MMR process (same eligible pool minus
       already-selected) for up to ``max_exploration`` more picks, each
       marked ``is_exploration=True``. Since step 1 already filtered to
       ``>= score_floor`` before any selection happens, an exploration pick
       can never be below-floor by construction.
    """
    eligible = sorted(
        (
            c
            for c in scored
            if c.total_score >= score_floor
            and (
                not exclude_fingerprints
                or compute_outfit_fingerprint(c.item_ids) not in exclude_fingerprints
            )
        ),
        key=lambda c: (-c.total_score, tuple(c.item_ids)),
    )
    limited_options = len(eligible) < 3

    if not eligible:
        return PortfolioResult(portfolio=[], limited_options=limited_options, gap_report=gap_report)

    selected: list[ScoredCandidate] = [eligible[0]]
    remaining = eligible[1:]

    max_main_size = portfolio_size_range[1]

    def pick_next() -> ScoredCandidate:
        best: ScoredCandidate | None = None
        best_key: tuple[float, tuple[str, ...]] | None = None
        for candidate in remaining:
            max_sim = max(jaccard_similarity(candidate, s) for s in selected)
            mmr_score = lambda_ * candidate.total_score - (1 - lambda_) * max_sim
            key = (-mmr_score, tuple(candidate.item_ids))
            if best_key is None or key < best_key:
                best_key = key
                best = candidate
        assert best is not None  # remaining is non-empty whenever this is called
        return best

    while remaining and len(selected) < max_main_size:
        next_pick = pick_next()
        selected.append(next_pick)
        remaining.remove(next_pick)

    portfolio = [PortfolioCandidate(candidate=c, is_exploration=False) for c in selected]

    exploration_count = 0
    while remaining and exploration_count < max_exploration:
        next_pick = pick_next()
        selected.append(next_pick)
        remaining.remove(next_pick)
        portfolio.append(PortfolioCandidate(candidate=next_pick, is_exploration=True))
        exploration_count += 1

    return PortfolioResult(portfolio=portfolio, limited_options=limited_options, gap_report=gap_report)
