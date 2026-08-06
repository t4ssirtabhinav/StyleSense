"""SS-038 -- Engine v2 stage ③'s novelty sub-term, split impure/pure.

``fetch_novelty_inputs`` is Engine v2's second (and last) I/O call --
``public.wear_recency()`` (SS-035, ``BL-119``'s first real caller) and
``suggestion_impressions`` history (SS-033). Both underlying ports are
ALREADY contractually never-raise (return ``[]`` on failure per their own
docstrings), so this function needs no try/except of its own to satisfy
"DB error degrades to neutral" -- it only needs to correctly build a neutral
``NoveltyInputs`` from empty inputs, which ``compute_novelty_score`` below
already does for any item absent from it.

``recent_impressions()`` is NOT occasion-filtered by its own port --
``recent_impression_item_counts`` deliberately counts impressions from
EVERY occasion (an item shown often anywhere is less novel to show again
anywhere), a different axis from ``wear_recency_by_item``'s occasion-scoped
fields. Do not conflate the two.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from adapters.interfaces import ISuggestionLogRepository, IWearHistoryRepository
from services.engine_v2_types import NoveltyInputs
from services.styling_rules_engine import _mean

__all__ = ["fetch_novelty_inputs", "compute_novelty_score"]

# 30-day lookback for "times shown recently" -- an Architect-assigned
# window, same unvalidated class as RULE_WEIGHTS (folds into BL-077).
RECENT_IMPRESSIONS_LOOKBACK_DAYS = 30

# _recency_item_score's own convention (styling_rules_engine.py): days-since
# saturates to 1.0 at 90 days. Mirrored here so novelty and wear-recency use
# the same "under 3 months ago is meaningfully recent" scale.
_NOVELTY_SATURATION_DAYS = 90


def _saturate(days: int | None, cap: int) -> float:
    """Mirrors ``_recency_item_score``'s existing ``min(1.0, days/cap)``
    convention. ``None`` days (never worn / no data) -> maximal novelty."""
    if days is None:
        return 1.0
    return min(1.0, max(0, days) / cap)


async def fetch_novelty_inputs(
    wear_history_repo: IWearHistoryRepository,
    suggestion_log_repo: ISuggestionLogRepository,
    *,
    jwt: str,
    user_id: str,
    occasion_key: str | None,
    as_of: date,
) -> NoveltyInputs:
    wear_recencies = await wear_history_repo.fetch_wear_recency(
        jwt=jwt, user_id=user_id, occasion_key=occasion_key
    )
    since = datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC) - timedelta(
        days=RECENT_IMPRESSIONS_LOOKBACK_DAYS
    )
    impressions = await suggestion_log_repo.recent_impressions(user_id=user_id, since=since)

    wear_recency_by_item = {wr.item_id: wr for wr in wear_recencies}

    recent_impression_item_counts: dict[str, int] = {}
    for impression in impressions:
        item_ids = impression.get("item_ids") or []
        for item_id in item_ids:
            recent_impression_item_counts[item_id] = (
                recent_impression_item_counts.get(item_id, 0) + 1
            )

    return NoveltyInputs(
        wear_recency_by_item=wear_recency_by_item,
        recent_impression_item_counts=recent_impression_item_counts,
    )


def compute_novelty_score(
    item_ids: list[str],
    occasion_key: str | None,
    inputs: NoveltyInputs,
    *,
    as_of: date,
) -> float:
    """Per item: ``days_since_occasion`` from ``last_worn_on_for_occasion``
    (``None`` -> maximal novelty, ``1.0``); ``days_since_any`` from
    ``last_worn_on`` similarly; ``times_shown`` from
    ``recent_impression_item_counts``. ``item_novelty = 0.5*saturate(days_since_occasion,
    90) + 0.3*saturate(days_since_any, 90) + 0.2*(1 - min(1.0, times_shown/5))``.

    When ``occasion_key is None`` (BL-121's Mark Worn case),
    ``days_since_occasion``'s term degrades to ``days_since_any``'s value
    instead of always being ``1.0``-by-absence -- novelty degrades to
    "global novelty," not "everything maximally novel." Candidate-level
    score is the mean over ``item_ids``."""
    item_scores: list[float] = []
    for item_id in item_ids:
        wear_recency = inputs.wear_recency_by_item.get(item_id)
        days_since_any: int | None = None
        days_since_occasion: int | None = None
        if wear_recency is not None:
            if wear_recency.last_worn_on is not None:
                days_since_any = (as_of - wear_recency.last_worn_on).days
            if wear_recency.last_worn_on_for_occasion is not None:
                days_since_occasion = (as_of - wear_recency.last_worn_on_for_occasion).days

        days_since_any_score = _saturate(days_since_any, _NOVELTY_SATURATION_DAYS)
        if occasion_key is None:
            days_since_occasion_score = days_since_any_score
        else:
            days_since_occasion_score = _saturate(days_since_occasion, _NOVELTY_SATURATION_DAYS)

        times_shown = inputs.recent_impression_item_counts.get(item_id, 0)
        item_novelty = (
            0.5 * days_since_occasion_score
            + 0.3 * days_since_any_score
            + 0.2 * (1 - min(1.0, times_shown / 5.0))
        )
        item_scores.append(item_novelty)

    return _mean(item_scores, default=1.0)
