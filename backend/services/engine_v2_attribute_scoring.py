"""SS-038 -- Engine v2 stage ③ (attribute scoring), pure.

Pairwise colour harmony (not star-topology), volume balance, register
coherence, fabric x weather, and occasion-aware novelty -- orchestrated into
one ``RuleScore`` list + weighted ``total_score`` per ``ENGINE_V2_RULE_WEIGHTS``.
Mirrors ``styling_rules_engine.score_candidate``'s shape exactly (same
``ScoredCandidate``/``RuleScore`` types), so ``render_candidate_for_prompt``
needs zero changes.

``category_completeness_score`` is moved verbatim from
``styling_rules_engine._category_completeness_score``. ``volume_balance_score``/
``register_coherence_score`` are NEW -- both degrade to "no signal for that
pair" (excluded from the mean, not scored as a fabricated 0 or 1) whenever
either item is fallback-path-only (``garment_lookup`` misses) or
(``volume_balance_score`` only) the resolved row's ``volume_class`` is
absent, per the raw ticket's own "neither bonus nor penalty" instruction.

``fabric_weather_score``'s BL-125 posture -- gated PER SUB-SIGNAL, not per
fabric row: ``season_affinity IS NULL`` (silk, khadi) skips only that
sub-signal; ``weight``/``breathability`` still combine into the other
sub-signal normally. The exact breathability-vs-season numeric thresholds
below are an Architect inference (design doc's own "Open questions" #2),
same unvalidated class as ``RULE_WEIGHTS``/``_hue_distance_score``'s
original thresholds -- folds into ``BL-077``'s future eval, not a blocker.
"""

from __future__ import annotations

import itertools
from datetime import date

from ai.ports.interfaces import SeasonTag
from services.engine_v2_candidate_search import (
    GarmentLookup,
    _formality_item_score,
    _occasion_tag_item_score,
    _recency_item_score,
    _season_item_score,
    _style_preference_item_bonus,
)
from services.engine_v2_colour import pairwise_colour_harmony
from services.engine_v2_novelty import compute_novelty_score
from services.engine_v2_types import (
    AssembledCandidate,
    FabricAttributes,
    GarmentAttributes,
    NoveltyInputs,
)
from services.styling_rules_defaults import CATEGORY_SLOT, ENGINE_V2_RULE_WEIGHTS
from services.styling_rules_engine import _clamp01, _mean
from services.styling_rules_types import (
    OccasionStylingInput,
    RuleScore,
    ScoredCandidate,
    StylePreferencesInput,
    StylingRulesOverride,
    WardrobeItemInput,
)

__all__ = [
    "category_completeness_score",
    "volume_balance_score",
    "register_coherence_score",
    "fabric_weather_score",
    "score_assembled_candidate",
]

_VOLUMINOUS_CLASSES = frozenset({"voluminous", "oversized"})
_VOLUME_CLASH_PENALTY = 0.6
_REGISTER_INCOHERENT_SCORE = 0.5

# Breathability 0-10 scale (fabrics.breathability's own CHECK range).
_HIGH_BREATHABILITY = 7
_LOW_BREATHABILITY_WINTER = 3
_MODERATE_BREATHABILITY_FLOOR = 4
_MONSOON_BREATHABILITY_RANGE = (5, 8)

_WEIGHT_SCORE_BY_SEASON: dict[str, dict[str, float]] = {
    "summer": {"light": 1.0, "medium": 0.7, "heavy": 0.3},
    "winter": {"heavy": 1.0, "medium": 0.7, "light": 0.3},
    "monsoon": {"light": 1.0, "medium": 0.6, "heavy": 0.3},
}


def category_completeness_score(
    items: list[WardrobeItemInput], rules: StylingRulesOverride
) -> float:
    """Moved verbatim from ``styling_rules_engine._category_completeness_score``."""
    components = [1.0]  # the base slot is always structurally valid by construction
    footwear_present = any(
        item.category is not None and CATEGORY_SLOT[item.category] == "footwear"
        for item in items
    )
    if rules.footwear_required:
        if footwear_present:
            preferred = set(rules.preferred_footwear_categories or [])
            matched = any(
                item.category is not None
                and CATEGORY_SLOT[item.category] == "footwear"
                and item.category in preferred
                for item in items
            )
            components.append(1.0 if (not preferred or matched) else 0.7)
        else:
            components.append(0.2)
    else:
        components.append(1.0 if footwear_present else 0.9)
    if rules.outerwear_required:
        outerwear_present = any(
            item.category is not None and CATEGORY_SLOT[item.category] == "outerwear"
            for item in items
        )
        components.append(1.0 if outerwear_present else 0.2)
    return sum(components) / len(components)


def _resolve_all(
    items: list[WardrobeItemInput], garment_lookup: GarmentLookup
) -> dict[str, GarmentAttributes]:
    resolved: dict[str, GarmentAttributes] = {}
    for item in items:
        if item.category is None:
            continue
        attrs = garment_lookup(item.category)
        if attrs is not None:
            resolved[item.id] = attrs
    return resolved


def volume_balance_score(items: list[WardrobeItemInput], garment_lookup: GarmentLookup) -> float:
    """For every pair where BOTH items resolve via ``garment_lookup`` and
    both have a non-``None`` ``volume_class``: penalize (0.6) when both are
    "voluminous"/"oversized"-class AND neither item's ``register`` includes
    "streetwear"; else 1.0. Any unresolved item or missing ``volume_class``
    contributes NO signal for that pair (excluded from the mean, not scored
    as 0) -- mean over scored pairs, 1.0 if no pair had a signal at all."""
    resolved = _resolve_all(items, garment_lookup)
    scores: list[float] = []
    for a, b in itertools.combinations(items, 2):
        attrs_a = resolved.get(a.id)
        attrs_b = resolved.get(b.id)
        if attrs_a is None or attrs_b is None:
            continue
        if attrs_a.volume_class is None or attrs_b.volume_class is None:
            continue
        both_voluminous = (
            attrs_a.volume_class in _VOLUMINOUS_CLASSES
            and attrs_b.volume_class in _VOLUMINOUS_CLASSES
        )
        neither_streetwear = (
            "streetwear" not in attrs_a.register and "streetwear" not in attrs_b.register
        )
        scores.append(_VOLUME_CLASH_PENALTY if (both_voluminous and neither_streetwear) else 1.0)
    return _mean(scores, default=1.0)


def register_coherence_score(
    items: list[WardrobeItemInput], garment_lookup: GarmentLookup
) -> float:
    """For every pair where both resolve via ``garment_lookup``: 1.0 if
    ``set(a.register) & set(b.register)`` is non-empty or ``b.key in
    a.pairs_with`` or ``a.key in b.pairs_with``; else 0.5. Same
    "unresolved pair contributes no signal" degrade as ``volume_balance_score``."""
    resolved = _resolve_all(items, garment_lookup)
    scores: list[float] = []
    for a, b in itertools.combinations(items, 2):
        attrs_a = resolved.get(a.id)
        attrs_b = resolved.get(b.id)
        if attrs_a is None or attrs_b is None:
            continue
        overlap = set(attrs_a.register) & set(attrs_b.register)
        pairs = attrs_b.key in attrs_a.pairs_with or attrs_a.key in attrs_b.pairs_with
        scores.append(1.0 if (overlap or pairs) else _REGISTER_INCOHERENT_SCORE)
    return _mean(scores, default=1.0)


def _breathability_weather_subscore(
    season: str, weight: str | None, breathability: int | None
) -> float | None:
    """The "(b)" sub-signal of ``fabric_weather_score`` -- ``None`` when
    neither ``weight`` nor ``breathability`` is populated, or ``season`` is
    outside the three named seasons (this heuristic has no opinion about
    ``"all"``)."""
    if weight is None and breathability is None:
        return None
    if season not in _WEIGHT_SCORE_BY_SEASON:
        return None

    components: list[float] = []
    if breathability is not None:
        if season == "summer":
            components.append(
                1.0
                if breathability >= _HIGH_BREATHABILITY
                else (0.6 if breathability >= _MODERATE_BREATHABILITY_FLOOR else 0.3)
            )
        elif season == "winter":
            components.append(
                1.0
                if breathability <= _LOW_BREATHABILITY_WINTER
                else (0.6 if breathability <= 6 else 0.3)
            )
        else:  # monsoon
            low, high = _MONSOON_BREATHABILITY_RANGE
            components.append(
                1.0
                if low <= breathability <= high
                else (0.6 if breathability >= _MODERATE_BREATHABILITY_FLOOR else 0.3)
            )
    if weight is not None:
        components.append(_WEIGHT_SCORE_BY_SEASON[season].get(weight, 0.5))

    return _mean(components, default=1.0) if components else None


def fabric_weather_score(
    items: list[WardrobeItemInput],
    fabric_attrs: dict[str, FabricAttributes],
    *,
    season: SeasonTag | None,
) -> float:
    """Per item: look up ``fabric_attrs.get(item.fabric)``; if ``season is
    None`` or no fabric row -> 1.0 (no opinion). Else combine, where
    populated: (a) ``season_affinity`` match (1.0 match, 0.4
    populated-but-no-match, SKIPPED if ``row.season_affinity is None`` --
    BL-125's gate, protects silk/khadi structurally); (b) the
    breathability/weight-vs-season heuristic above. Mean of whichever
    sub-signals are actually populated for that item; 1.0 if none are.
    Candidate-level score is the mean over items; 1.0 if no item has a
    populated fabric anywhere."""
    item_scores: list[float] = []
    for item in items:
        row = fabric_attrs.get(item.fabric) if item.fabric else None
        if season is None or row is None:
            item_scores.append(1.0)
            continue
        sub_scores: list[float] = []
        if row.season_affinity is not None:
            sub_scores.append(1.0 if season in row.season_affinity else 0.4)
        breathability_component = _breathability_weather_subscore(
            season, row.weight, row.breathability
        )
        if breathability_component is not None:
            sub_scores.append(breathability_component)
        item_scores.append(_mean(sub_scores, default=1.0))
    return _mean(item_scores, default=1.0)


def score_assembled_candidate(
    candidate: AssembledCandidate,
    occasion: OccasionStylingInput,
    rules: StylingRulesOverride,
    *,
    garment_lookup: GarmentLookup,
    fabric_attrs: dict[str, FabricAttributes],
    novelty_inputs: NoveltyInputs,
    as_of: date,
    season: SeasonTag | None,
    style_preferences: StylePreferencesInput | None,
) -> ScoredCandidate:
    """Orchestrates all ten ``ENGINE_V2_RULE_WEIGHTS`` terms into one
    ``RuleScore`` list + weighted ``total_score``. Mirrors
    ``styling_rules_engine.score_candidate``'s shape exactly."""
    items = candidate.items
    tolerance = (
        rules.formality_tolerance if rules.formality_tolerance is not None else 2
    )

    formality_scores = [_formality_item_score(i, occasion.formality, tolerance) for i in items]
    formality_fit = _mean(formality_scores, default=0.0)

    completeness = category_completeness_score(items, rules)
    colour_harmony = pairwise_colour_harmony(items)
    volume_balance = volume_balance_score(items, garment_lookup)
    register_coherence = register_coherence_score(items, garment_lookup)
    fabric_weather = fabric_weather_score(items, fabric_attrs, season=season)

    recency_scores = [
        min(
            1.0,
            _recency_item_score(item, as_of)
            + 0.15 * _style_preference_item_bonus(item, style_preferences),
        )
        for item in items
    ]
    wear_recency = _mean(recency_scores, default=0.0)

    occasion_scores = [_occasion_tag_item_score(i, occasion.key) for i in items]
    occasion_tag_bonus = _mean(occasion_scores, default=0.0)

    season_scores = [_season_item_score(i, season) for i in items]
    season_fit = _mean(season_scores, default=1.0)

    novelty = compute_novelty_score(
        [item.id for item in items], occasion.key, novelty_inputs, as_of=as_of
    )

    components: dict[str, float] = {
        "formality_fit": formality_fit,
        "category_completeness": completeness,
        "colour_harmony": colour_harmony,
        "volume_balance": volume_balance,
        "register_coherence": register_coherence,
        "fabric_weather": fabric_weather,
        "wear_recency": wear_recency,
        "novelty": novelty,
        "occasion_tag_bonus": occasion_tag_bonus,
        "season_fit": season_fit,
    }

    matched_occasion_count = sum(1 for s in occasion_scores if s >= 1.0)
    explanations: dict[str, str] = {
        "formality_fit": f"Formality fit {formality_fit:.2f} (tolerance {tolerance})",
        "category_completeness": f"Outfit completeness {completeness:.2f}",
        "colour_harmony": f"Colour harmony {colour_harmony:.2f}",
        "volume_balance": f"Volume balance {volume_balance:.2f}",
        "register_coherence": f"Register coherence {register_coherence:.2f}",
        "fabric_weather": f"Fabric x weather fit {fabric_weather:.2f}",
        "wear_recency": f"Favours under-worn items ({wear_recency:.2f})",
        "novelty": f"Novelty {novelty:.2f}",
        "occasion_tag_bonus": f"{matched_occasion_count}/{len(items)} items tagged {occasion.key}",
        "season_fit": f"Season fit {season_fit:.2f}",
    }

    rule_scores = [
        RuleScore(rule=name, score=round(_clamp01(score), 4), explanation=explanations[name])
        for name, score in components.items()
    ]
    total = sum(ENGINE_V2_RULE_WEIGHTS[r.rule] * r.score for r in rule_scores)
    return ScoredCandidate(
        item_ids=[item.id for item in items],
        category_labels={item.id: item.category for item in items if item.category},
        total_score=round(_clamp01(total), 4),
        rule_scores=rule_scores,
        gap_flags=list(candidate.gap_flags),
    )
