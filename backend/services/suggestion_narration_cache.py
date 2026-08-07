"""SS-020 -- the combination-signature cache: pure signature computation
plus never-raising cache read/write orchestration.

**What is cached:** only the LLM's *prose*, never Engine v2's item-level
selection (which stays 100% per-user, computed fresh every request). By the
time anything is cached, the *set of candidates* has already been fully and
independently personalised per user; the cache only asks "has an LLM
already narrated a candidate set that looks like this one (by coarse
attribute shape), for this occasion?"

**Deviation from the design doc's literal ``compute_narration_signature``
signature, flagged explicitly (not silently improvised):** the design doc's
own sketch types the ``candidates`` parameter as
``render_candidate_for_prompt(...)`` output (``list[dict[str, Any]]``), but
that function's actual output (``styling_rules_engine.render_candidate_for_prompt``)
only carries per-item CATEGORY LABELS (human strings) and a joined
explanation string -- it never carries raw colour hex or a formality score,
both of which the design's own coarsening algorithm (Concrete Values #3
step 1: "sorted tuple of (category, colour_family_bucket, formality_band)
per item") structurally requires. This module instead computes the
signature from ``ScoredCandidate.item_ids`` plus the same
``WardrobeItemInput`` lookup the orchestrator already holds in scope at
that point (pre-render) -- ``compute_candidate_shape`` below -- which is
the only place in the actual pipeline that has raw ``color_primary`` hex
and category enum values simultaneously. The exact coarsening SEMANTICS
(category, colour-family-bucket, formality-band tuples; salted HMAC;
order-independent) are unchanged from the design; only the Python type
used to reach them differs from the doc's literal sketch.

**``colour_family_bucket``, flagged as a Developer gap-fill distinct from
``BL-064``/``BL-079``:** the design doc says this reuses
"``HARD_EXCLUDED_COLOR_FAMILIES``'s existing hue-bucket vocabulary" -- but
that dict (``styling_rules_defaults.HARD_EXCLUDED_COLOR_FAMILIES``) is NOT
a hue-bucket vocabulary; it is a one-entry occasion-exclusion map
(``{"wedding_guest": frozenset({"white"})}``). No hex-to-colour-family
binning function exists anywhere in this codebase yet --
``engine_v2_colour.py``'s own module docstring and ``BL-064``/``BL-079``
explicitly say that binning is NOT YET BUILT ("needs BL-064/BL-079's
hex-to-colour-family binning first, deliberately not built here"). This
module therefore defines its own minimal 9-bucket hue binning
(``_colour_family_bucket`` below), narrowly scoped to cache-key coarsening
ONLY -- it is never used for any correctness-affecting exclusion/scoring
decision, so it does not resolve BL-064/BL-079 (that ticket needs a
product-validated vocabulary for CORRECTNESS, not just cache-sharing) and
does not claim to. Flagged in the worklog, not silently invented.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

from adapters.interfaces import CachedNarration, ISuggestionNarrationCacheRepository
from services.engine_v2_colour import hex_to_hsv
from services.styling_rules_defaults import CATEGORY_FORMALITY
from services.styling_rules_types import WardrobeItemInput

logger = logging.getLogger(__name__)

__all__ = [
    "CandidateShape",
    "compute_candidate_shape",
    "compute_narration_signature",
    "signature_order",
    "NarrationCacheOrchestrator",
]

# One tuple per item: (category, colour_family_bucket, formality_band).
CandidateShape = tuple[tuple[str, str, int], ...]

# 8 hue buckets (45 degrees each) + "neutral" (near-grey/black/white,
# reusing engine_v2_colour's own near-white-adjacent saturation notion) +
# "unknown" (unparsable/missing colour). Cache-coarsening only -- see
# module docstring.
_NEUTRAL_SATURATION_CUTOFF = 0.15
_HUE_BUCKETS = (
    "red",
    "orange",
    "yellow",
    "green",
    "cyan",
    "blue",
    "purple",
    "pink",
)


def _colour_family_bucket(hex_color: str | None) -> str:
    if hex_color is None:
        return "unknown"
    hsv = hex_to_hsv(hex_color)
    if hsv is None:
        return "unknown"
    hue, saturation, _value = hsv
    if saturation <= _NEUTRAL_SATURATION_CUTOFF:
        return "neutral"
    # Shifted by half a bucket-width (22.5deg) so "red" is CENTRED on hue 0
    # (pure red) rather than straddling the 0/360 wraparound boundary --
    # without this, two near-identical reds (e.g. hue 358 and hue 2) would
    # fall into different buckets, defeating the whole point of coarsening.
    shifted_degrees = ((hue * 360.0) + 22.5) % 360.0
    bucket_index = int(shifted_degrees // 45.0) % len(_HUE_BUCKETS)
    return _HUE_BUCKETS[bucket_index]


def _formality_band(category: str | None) -> int:
    """Rounds a category's base formality (0-10 scale) to the nearest band
    of 2 (0/2/4/6/8/10), per the user's signed-off coarsening granularity
    (docs/worklog/SS-020.md's Open Questions sign-off #2). ``category=None``
    (an untagged item slipped through) -> band -1, a value no real
    formality score can ever produce, so it never collides with a real
    band."""
    if category is None or category not in CATEGORY_FORMALITY:
        return -1
    raw = CATEGORY_FORMALITY[category]
    band = round(raw / 2.0) * 2
    return max(0, min(10, band))


def compute_candidate_shape(
    item_ids: list[str], wardrobe_by_id: dict[str, WardrobeItemInput]
) -> CandidateShape:
    """One candidate's coarse, sorted (item-order-independent) shape.
    NEVER the raw hex, NEVER the item id -- only (category,
    colour_family_bucket, formality_band) per item."""
    item_tuples = []
    for item_id in item_ids:
        item = wardrobe_by_id.get(item_id)
        category = item.category if item is not None else None
        colour_bucket = _colour_family_bucket(item.color_primary if item is not None else None)
        formality_band = _formality_band(category)
        item_tuples.append((str(category), colour_bucket, formality_band))
    return tuple(sorted(item_tuples))


def compute_narration_signature(
    candidate_shapes: list[CandidateShape],
    *,
    occasion_key: str,
    engine_version: str,
    llm_candidate_count: int,
) -> str:
    """Order-independent across the candidate list (candidates themselves
    sorted by their own tuple-of-tuples) but sensitive to occasion/
    engine_version/llm_candidate_count/category/colour-family/formality-band
    changes. A SALTED, KEYED hash (HMAC-SHA256), not a plain sha256 --
    closes the "brute-force common wardrobes to probe which signatures are
    cache-warm" angle at zero extra cost.

    ``SUGGESTION_CACHE_SALT`` is a required env var -- see
    ``docs/worklog/SS-020.md``'s Developer entry for provisioning status."""
    sorted_shapes = sorted(candidate_shapes)
    shape_string = f"{occasion_key}|{engine_version}|{llm_candidate_count}|" + "||".join(
        ",".join(f"{category}:{colour}:{formality}" for category, colour, formality in shape)
        for shape in sorted_shapes
    )
    salt = os.environ["SUGGESTION_CACHE_SALT"]
    return hmac.new(salt.encode("utf-8"), shape_string.encode("utf-8"), hashlib.sha256).hexdigest()


def signature_order(candidate_shapes: list[CandidateShape]) -> list[int]:
    """Returns the ORIGINAL indices in the same sorted order
    ``compute_narration_signature`` hashes them in -- i.e.
    ``order[signature_index] == original_index``. Deterministic tie-break on
    the original index for candidates with an identical shape, so this is a
    genuine permutation (never ambiguous) even with duplicate shapes."""
    return sorted(range(len(candidate_shapes)), key=lambda i: (candidate_shapes[i], i))


class NarrationCacheOrchestrator:
    """Wraps ``ISuggestionNarrationCacheRepository`` with a defensive
    try/except belt-and-suspenders even though the port's own contract
    already says MUST NEVER RAISE (mirrors this repo's established
    "belt and suspenders" posture for every never-raise port, e.g.
    ``EngineV2._log_session``). A cache failure degrades to "always call
    the LLM," never to a failed request."""

    def __init__(self, repository: ISuggestionNarrationCacheRepository) -> None:
        self._repository = repository

    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        try:
            return await self._repository.get(signature_hash=signature_hash)
        except Exception as exc:  # noqa: BLE001 -- cache read must never fail a suggestion request
            logger.warning("suggestion_narration_cache_get_failed", extra={"error": str(exc)})
            return None

    async def put(
        self,
        *,
        signature_hash: str,
        occasion_key: str,
        engine_version: str,
        narrations_by_signature_index: dict[int, str],
        language: str,
        ttl_seconds: int,
    ) -> None:
        try:
            await self._repository.put(
                signature_hash=signature_hash,
                occasion_key=occasion_key,
                engine_version=engine_version,
                narrations_by_signature_index=narrations_by_signature_index,
                language=language,
                ttl_seconds=ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001 -- cache write must never fail a suggestion request
            logger.warning("suggestion_narration_cache_put_failed", extra={"error": str(exc)})
