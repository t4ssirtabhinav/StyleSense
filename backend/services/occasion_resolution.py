"""SS-048 -- ``resolve_occasion_input``, extracted VERBATIM from
``OutfitPortfolioService._resolve_occasion`` (SS-020) so both the live
``POST /outfit-suggestions/portfolio`` endpoint and the new rail precompute
job (``services/rail_precompute_service.py``) resolve an occasion string the
SAME way -- one implementation, not two.

Pure extract-method refactor: behavior is byte-identical to the pre-SS-048
private method. ``OutfitPortfolioService._resolve_occasion`` becomes a
one-line delegation to this function (see that module) -- the existing
SS-020/22/23 test suite for that file is the regression guard proving this.
"""

from __future__ import annotations

from services.occasion_normalizer import OccasionNormalizer
from services.styling_rules_types import OccasionStylingInput

_FALLBACK_OCCASION_KIND = "everyday"
_FALLBACK_OCCASION_FORMALITY = 5


async def resolve_occasion_input(
    raw_occasion: str, *, jwt: str, occasion_normalizer: OccasionNormalizer
) -> OccasionStylingInput:
    """§2 step 1 (SS-020 design). An unresolvable/unknown occasion (not in
    ``snapshot.kinds``, no alias hit) still gets a full
    kind/formality/styling_rules triple -- degrades to
    ``kind="everyday", formality=5, styling_rules={}`` rather than a
    400/500 (mirrors ``default_styling_rules_for``'s own kind-based
    fallback philosophy). The occasion key itself is passed through
    VERBATIM (not replaced with a sentinel) so downstream novelty/
    gap-flag logging still records the unmodelled key for later review."""
    snapshot = await occasion_normalizer.get_registry(jwt=jwt)
    resolved_key = occasion_normalizer.resolve(raw_occasion, snapshot)
    if not resolved_key:
        resolved_key = _FALLBACK_OCCASION_KIND

    if resolved_key in snapshot.kinds:
        return OccasionStylingInput(
            key=resolved_key,
            kind=snapshot.kinds[resolved_key],  # type: ignore[arg-type]
            formality=snapshot.formalities.get(resolved_key, _FALLBACK_OCCASION_FORMALITY),
            styling_rules=snapshot.styling_rules.get(resolved_key, {}),
        )

    return OccasionStylingInput(
        key=resolved_key,
        kind=_FALLBACK_OCCASION_KIND,  # type: ignore[arg-type]
        formality=_FALLBACK_OCCASION_FORMALITY,
        styling_rules={},
    )
