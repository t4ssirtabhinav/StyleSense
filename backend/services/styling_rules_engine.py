"""SS-027 -- Styling Rules Engine & Deterministic Pre-Filter.

**Superseded by Engine v2 (SS-038) for candidate generation and scoring.**
``generate_candidates``/``score_candidate`` and their private helpers
(``_dedupe_by_id``, ``_resolve_styling_rules``, ``_group_by_slot``,
``_rank_within_slot``, ``_build_base_combinations``, the six per-item
scorers, ``_category_completeness_score``, ``_colour_harmony_score``,
``_hex_to_hsv``, ``_is_near_white``, ``_item_is_hard_excluded_white``,
``_hue_distance_score``) are GONE from this file -- MOVED, not duplicated,
into ``services/engine_v2_eligibility.py`` (stage①), ``engine_v2_candidate_search.py``
(stage②), ``engine_v2_attribute_scoring.py`` (stage③), and
``engine_v2_colour.py`` (the shared colour primitives both stages ①/③ use).
``EngineV2.generate_portfolio`` (``services/engine_v2.py``) is the new
entry point; see that module's docstring for exactly which of this file's
named gaps (below) it fixes, by stage, and which ``BL-XXX`` rows remain
open.

**The only remaining public surface is ``render_candidate_for_prompt``** --
"the sole, only path from a scored candidate to LLM-facing text" is
unchanged, because ``ScoredCandidate``'s shape never changed: Engine v2's
stage③ (``engine_v2_attribute_scoring.score_assembled_candidate``) produces
the exact same ``ScoredCandidate``/``RuleScore`` types this function always
consumed, so it needed zero edits. A future prompt-builder must still call
``render_candidate_for_prompt`` rather than re-deriving colour/formality
text itself -- this is what keeps "two copies will drift" structurally
impossible.

Pure, offline, side-effect-free: no DB I/O, no network I/O, no system clock
reads (unchanged from SS-027).

Colour harmony and formality-distance scoring are v1 heuristics -- an
inference, not a verified colour-theory/stylist standard. Real quality
validation is tracked by `BL-077` (Epic 3's unrun AI eval), not this
ticket's to run.

SS-037 (v0 fix pass) closed the "which outfits are even expressible" half of
SS-027's known holes (named-colour white guard, outerwear assembly, dupatta
attachability). SS-038 (Engine v2) fixes the rest, named here for a reader
who lands on this docstring first rather than ``engine_v2.py``'s:

- Footwear/accessory/outerwear selection was a function of the item alone,
  never of the base -- the same shoe/jacket/accessory could appear on every
  candidate. FIXED by Engine v2 stage② (wide search, top-N-per-remaining-
  slot expansion) + stage④ (MMR portfolio diversity).
- Colour was absent from the per-slot capping formula (`MAX_ITEMS_PER_SLOT`
  capping happened before `_colour_harmony_score` was ever called). FIXED by
  Engine v2 stage② (folded into the base-ranking key).
- `_colour_harmony_score` was star-topology (everything compared to
  `colored[0]`, order-dependent). FIXED by Engine v2 stage③'s
  `pairwise_colour_harmony` (resolves `BL-128`'s star-topology half;
  `_hue_distance_score`'s flat `0.75` unparsable-colour fallback is
  DELIBERATELY still open -- see `engine_v2_colour.py`).
- The near-white HSV threshold was a hardcoded Python literal. FIXED by
  Engine v2 -- now an `app_config` row with a per-occasion override path
  (resolves `BL-111`).
- `engine_version` was never bumped on any suggestion-log row. FIXED --
  Engine v2 writes `"engine-v2"` (resolves `BL-114`).
- `wear_recency()`/`IWearHistoryRepository` had zero callers. FIXED --
  Engine v2's novelty stage is the first real caller (resolves `BL-119`).
- `suggestion_impressions` had no real caller, only test fixtures. FIXED --
  Engine v2 is the first real writer.
"""

from __future__ import annotations

from typing import Any

from services.styling_rules_types import ScoredCandidate

__all__ = ["render_candidate_for_prompt"]


def render_candidate_for_prompt(candidate: ScoredCandidate) -> dict[str, Any]:
    """The exact, only, LLM-input-shaping function. A future prompt template
    calls this per candidate and concatenates -- it must never re-derive
    colour/formality text itself."""
    top_explanations = sorted(candidate.rule_scores, key=lambda r: -r.score)[:2]
    return {
        "items": [
            {"id": item_id, "category": candidate.category_labels.get(item_id, "")}
            for item_id in candidate.item_ids
        ],
        "score": round(candidate.total_score, 3),
        "explanation": "; ".join(r.explanation for r in top_explanations),
        "gap_flags": list(candidate.gap_flags),
    }


# ---------------------------------------------------------------------------
# Internal: small numeric helpers -- kept here (not moved) and imported by
# the new Engine v2 stage modules rather than re-implemented, per the design
# doc's explicit instruction.
# ---------------------------------------------------------------------------


def _mean(values: list[float], *, default: float) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
