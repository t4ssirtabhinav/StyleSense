"""SS-027 -- Styling Rules Engine & Deterministic Pre-Filter.

**One rules module, consumed twice -- non-negotiable** (raw ticket's own
Technical Notes). Colour theory, formality matching, and occasion
constraints live here and ONLY here. A future prompt-builder must call
``render_candidate_for_prompt`` -- the sole, only path from a scored
candidate to LLM-facing text -- rather than re-deriving colour/formality
text itself. This is what makes "two copies will drift" structurally
impossible rather than merely discouraged.

Pure, offline, side-effect-free: no DB I/O, no network I/O, no system clock
reads. ``as_of``/``season`` are always explicit caller-supplied parameters
-- this module never calls ``date.today()`` -- which is what makes
"deterministic: same input, same output, every time" actually true (see
``test_as_of_is_never_read_from_system_clock`` /
``test_deterministic_same_input_same_output``).

Bounding the combinatorics: items are ranked and capped to
``MAX_ITEMS_PER_SLOT`` (default 8) per slot BEFORE any combination happens.
Base pool is <=8 (one_piece) + <=64 (8x8 top/bottom pairs) = <=72,
independent of wardrobe size once capped; each base then considers at most
one best-fit footwear and one bonus accessory, so worst-case combine work is
bounded at roughly 72 assembled+scored candidates regardless of whether the
input wardrobe has 1 or 5,000 items -- the only O(n) part is the single
precompute-and-rank pass per item.

Colour harmony (`_hue_distance_score`) and formality-distance scoring are
v1 heuristics -- an inference, not a verified colour-theory/stylist standard.
Real quality validation is tracked by `BL-077` (Epic 3's unrun AI eval), not
this ticket's to run.

SS-037 (v0 fix pass) closed the "which outfits are even expressible" half of
SS-027's known holes (named-colour white guard, outerwear assembly, dupatta
attachability). The following gaps are DELIBERATELY left unfixed here --
named so a future reader does not re-derive them as new findings:

- Footwear/accessory (and now outerwear) selection is a function of the item
  alone, never of the base -- the same shoe/jacket/accessory can appear on
  every candidate. Fixed by Engine v2 stage (2) (wide search) + stage (4)
  (MMR portfolio diversity).
- Colour is absent from the per-slot capping formula (`MAX_ITEMS_PER_SLOT`
  capping happens before `_colour_harmony_score` is ever called). Fixed by
  Engine v2 stage (2).
- `_colour_harmony_score` is star-topology (everything compared to
  `colored[0]`, order-dependent). Fixed by Engine v2 stage (3).
- `_hue_distance_score`'s flat `0.75` fallback for a named/unparsable colour
  degrades general colour-harmony scoring for such items at *any* occasion
  (distinct from the `wedding_guest` hard-exclusion guard, which SS-037 does
  fix) -- needs the same hex-to-colour-family binning work as `BL-064`/
  `BL-079`'s open colour half, deliberately not built here (tracked as
  `BL-128`).
- The near-white HSV threshold (`value >= 0.92, saturation <= 0.12`) is
  untouched -- cream/ivory/gold-cream banarasi may be over-excluded at
  `wedding_guest`; a cultural/product decision, not a threshold-tuning
  exercise (`BL-111`).
- No occasion kind currently sets the new `outerwear_required` flag, so the
  "missing_outerwear" gap-flag path is real code but currently reachable
  only via an explicit `styling_rules` override, never a live default
  (tracked as `BL-129`).
"""

from __future__ import annotations

import colorsys
from datetime import date
from typing import Any

from ai.ports.interfaces import SeasonTag
from services.styling_rules_defaults import (
    CATEGORY_FORMALITY,
    CATEGORY_SLOT,
    HARD_EXCLUDED_COLOR_FAMILIES,
    MAX_ITEMS_PER_SLOT,
    NEAR_WHITE_SATURATION_THRESHOLD,
    NEAR_WHITE_VALUE_THRESHOLD,
    RULE_WEIGHTS,
    default_styling_rules_for,
)
from services.styling_rules_types import (
    GapReport,
    OccasionStylingInput,
    PreFilterResult,
    RuleScore,
    ScoredCandidate,
    StylePreferencesInput,
    StylingRulesOverride,
    WardrobeItemInput,
)

__all__ = ["generate_candidates", "score_candidate", "render_candidate_for_prompt"]

_ALL_SLOTS: tuple[str, ...] = ("top", "bottom", "one_piece", "outerwear", "footwear", "accessory")
_DEFAULT_FORMALITY_TOLERANCE = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_candidates(
    wardrobe: list[WardrobeItemInput],
    occasion: OccasionStylingInput,
    *,
    as_of: date,
    season: SeasonTag | None = None,
    style_preferences: StylePreferencesInput | None = None,
    max_candidates: int = 5,
) -> PreFilterResult:
    """The entry point. ``as_of`` is required and keyword-only, never
    ``date.today()`` called internally -- see module docstring."""
    deduped = _dedupe_by_id(wardrobe)

    excluded_missing = sum(
        1 for item in deduped if item.category is None or item.color_primary is None
    )
    eligible = [
        item for item in deduped if item.category is not None and item.color_primary is not None
    ]

    rules = _resolve_styling_rules(occasion)
    hard_families = HARD_EXCLUDED_COLOR_FAMILIES.get(occasion.key, frozenset())
    effective_excluded = set(rules.excluded_color_families or []) | hard_families

    if "white" in effective_excluded:
        # Code-level, unconditional guard (never a prompt-level instruction)
        # -- applied regardless of what styling_rules contains or omits.
        eligible = [item for item in eligible if not _item_is_hard_excluded_white(item)]

    grouped = _group_by_slot(eligible)
    missing_slots = sorted(slot for slot in _ALL_SLOTS if not grouped[slot])

    tolerance = (
        rules.formality_tolerance
        if rules.formality_tolerance is not None
        else _DEFAULT_FORMALITY_TOLERANCE
    )

    def rank_key(item: WardrobeItemInput) -> float:
        return (
            0.35 * _formality_item_score(item, occasion.formality, tolerance)
            + 0.25 * _recency_item_score(item, as_of)
            + 0.15 * _season_item_score(item, season)
            + 0.15 * _occasion_tag_item_score(item, occasion.key)
            + 0.10 * _style_preference_item_bonus(item, style_preferences)
        )

    ranked_slots = {slot: _rank_within_slot(grouped[slot], rank_key) for slot in _ALL_SLOTS}

    required_base = rules.required_base or "either"
    bases = _build_base_combinations(ranked_slots, required_base)

    preferred_footwear = set(rules.preferred_footwear_categories or [])
    preferred_accessory = set(rules.preferred_accessory_categories or [])

    def footwear_key(item: WardrobeItemInput) -> float:
        bonus = 0.2 if item.category in preferred_footwear else 0.0
        return rank_key(item) + bonus

    def accessory_key(item: WardrobeItemInput) -> float:
        bonus = 0.2 if item.category in preferred_accessory else 0.0
        return rank_key(item) + bonus

    assembled: list[tuple[list[WardrobeItemInput], list[str]]] = []
    for base in bases:
        items = list(base)
        gap_flags: list[str] = []

        footwear_options = ranked_slots["footwear"]
        if footwear_options:
            best_footwear = sorted(footwear_options, key=lambda i: (-footwear_key(i), i.id))[0]
            items.append(best_footwear)
        elif rules.footwear_required:
            # Never dropped -- kept as a partial candidate with an explicit
            # gap flag (raw ticket's own edge case).
            gap_flags.append("missing_footwear")

        outerwear_options = ranked_slots["outerwear"]
        if outerwear_options:
            # Mirrors the footwear pattern directly above: attach the top-ranked
            # item whenever the wardrobe has one, unconditionally -- exactly like
            # footwear is attached regardless of footwear_required. The flag only
            # gates the ABSENCE case below, matching footwear_required's existing
            # role. ranked_slots["outerwear"] is already sorted by rank_key (item
            # alone) at line 119, so [0] is deterministic; it carries the same
            # known non-determinism as footwear/accessory selection across bases
            # (Engine v2's job -- see module docstring), not a new gap.
            items.append(outerwear_options[0])
        elif rules.outerwear_required:
            gap_flags.append("missing_outerwear")

        if preferred_accessory:
            for category in sorted(preferred_accessory):
                # One best item per preferred category, not one overall -- lets a
                # ceremony/festival/religious candidate carry a dupatta AND
                # jewellery simultaneously (raw ticket AC). sorted() over the set
                # gives deterministic category iteration order; the accessory_key
                # tiebreak within each category (score desc, id asc) is already
                # deterministic.
                category_options = [
                    i for i in ranked_slots["accessory"] if i.category == category
                ]
                if category_options:
                    best_in_category = sorted(
                        category_options, key=lambda i: (-accessory_key(i), i.id)
                    )[0]
                    items.append(best_in_category)

        assembled.append((items, gap_flags))

    scored: list[ScoredCandidate] = []
    for items, gap_flags in assembled:
        total_score, rule_scores = score_candidate(
            items,
            occasion,
            rules,
            as_of=as_of,
            season=season,
            style_preferences=style_preferences,
        )
        scored.append(
            ScoredCandidate(
                item_ids=[item.id for item in items],
                category_labels={item.id: item.category for item in items if item.category},
                total_score=total_score,
                rule_scores=rule_scores,
                gap_flags=gap_flags,
            )
        )

    # Deterministic ordering: score desc, item_ids tuple asc as tiebreak.
    scored.sort(key=lambda c: (-c.total_score, tuple(c.item_ids)))

    limited_options = len(scored) < 3
    candidates = scored[:max_candidates]

    return PreFilterResult(
        candidates=candidates,
        limited_options=limited_options,
        gap_report=GapReport(
            excluded_missing_color_or_category=excluded_missing,
            missing_slots=missing_slots,
        ),
    )


def score_candidate(
    items: list[WardrobeItemInput],
    occasion: OccasionStylingInput,
    rules: StylingRulesOverride,
    *,
    as_of: date,
    season: SeasonTag | None,
    style_preferences: StylePreferencesInput | None,
) -> tuple[float, list[RuleScore]]:
    """Scores one already-assembled combination. Exposed publicly so a
    future ticket can score a single user-assembled outfit outside the
    generation path (e.g. "why did the AI suggest this" on an existing
    ``outfits`` row) without re-deriving the formula."""
    tolerance = (
        rules.formality_tolerance
        if rules.formality_tolerance is not None
        else _DEFAULT_FORMALITY_TOLERANCE
    )

    formality_scores = [_formality_item_score(i, occasion.formality, tolerance) for i in items]
    formality_fit = _mean(formality_scores, default=0.0)

    completeness = _category_completeness_score(items, rules)

    colour_harmony = _colour_harmony_score(items)

    recency_scores = [
        min(1.0, _recency_item_score(item, as_of) + 0.15 * _style_preference_item_bonus(
            item, style_preferences
        ))
        for item in items
    ]
    wear_recency = _mean(recency_scores, default=0.0)

    occasion_scores = [_occasion_tag_item_score(i, occasion.key) for i in items]
    occasion_tag_bonus = _mean(occasion_scores, default=0.0)

    season_scores = [_season_item_score(i, season) for i in items]
    season_fit = _mean(season_scores, default=1.0)

    components: dict[str, float] = {
        "formality_fit": formality_fit,
        "category_completeness": completeness,
        "colour_harmony": colour_harmony,
        "wear_recency": wear_recency,
        "occasion_tag_bonus": occasion_tag_bonus,
        "season_fit": season_fit,
    }

    matched_occasion_count = sum(1 for s in occasion_scores if s >= 1.0)
    explanations: dict[str, str] = {
        "formality_fit": f"Formality fit {formality_fit:.2f} (tolerance {tolerance})",
        "category_completeness": f"Outfit completeness {completeness:.2f}",
        "colour_harmony": f"Colour harmony {colour_harmony:.2f}",
        "wear_recency": f"Favours under-worn items ({wear_recency:.2f})",
        "occasion_tag_bonus": f"{matched_occasion_count}/{len(items)} items tagged {occasion.key}",
        "season_fit": f"Season fit {season_fit:.2f}",
    }

    rule_scores = [
        RuleScore(
            rule=name,
            score=round(_clamp01(score), 4),
            explanation=explanations[name],
        )
        for name, score in components.items()
    ]
    total = sum(RULE_WEIGHTS[r.rule] * r.score for r in rule_scores)
    return round(_clamp01(total), 4), rule_scores


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
# Internal: styling rules resolution
# ---------------------------------------------------------------------------


def _resolve_styling_rules(occasion: OccasionStylingInput) -> StylingRulesOverride:
    """Parses ``occasion.styling_rules``, degrades to
    ``default_styling_rules_for(occasion.kind)`` on empty/unparseable
    fields, then layers any successfully-parsed override field on top of
    that base -- partial overrides work (e.g. a hand-edited
    ``{"formality_tolerance": 0}`` only changes that one field)."""
    base = default_styling_rules_for(occasion.kind)
    parsed = StylingRulesOverride.parse_lenient(occasion.styling_rules)
    merged: dict[str, Any] = {}
    for name in StylingRulesOverride.model_fields:
        value = getattr(parsed, name)
        merged[name] = value if value is not None else getattr(base, name)
    return StylingRulesOverride(**merged)


# ---------------------------------------------------------------------------
# Internal: grouping / ranking / combination
# ---------------------------------------------------------------------------


def _dedupe_by_id(wardrobe: list[WardrobeItemInput]) -> list[WardrobeItemInput]:
    """A caller bug or test fixture could construct duplicate ids (the real
    DB PK prevents this) -- dedupe by id, keep first occurrence, rather than
    let a duplicate silently double-count in a candidate."""
    seen: set[str] = set()
    result: list[WardrobeItemInput] = []
    for item in wardrobe:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result


def _group_by_slot(items: list[WardrobeItemInput]) -> dict[str, list[WardrobeItemInput]]:
    groups: dict[str, list[WardrobeItemInput]] = {slot: [] for slot in _ALL_SLOTS}
    for item in items:
        if item.category is None:
            continue
        groups[CATEGORY_SLOT[item.category]].append(item)
    return groups


def _rank_within_slot(
    items: list[WardrobeItemInput], key_fn: Any
) -> list[WardrobeItemInput]:
    """Sort deterministically (score desc, then id asc as the tiebreak) and
    cap to ``MAX_ITEMS_PER_SLOT`` before any combination happens."""
    ranked = sorted(items, key=lambda i: (-key_fn(i), i.id))
    return ranked[:MAX_ITEMS_PER_SLOT]


def _build_base_combinations(
    ranked_slots: dict[str, list[WardrobeItemInput]], required_base: str
) -> list[list[WardrobeItemInput]]:
    bases: list[list[WardrobeItemInput]] = []
    if required_base in ("one_piece", "either"):
        for item in ranked_slots["one_piece"]:
            bases.append([item])
    if required_base in ("top_bottom", "either"):
        for top in ranked_slots["top"]:
            for bottom in ranked_slots["bottom"]:
                bases.append([top, bottom])
    return bases


# ---------------------------------------------------------------------------
# Internal: per-item scoring components (shared by ranking AND score_candidate
# -- the single implementation both the capper and the final scorer call, so
# there is no second copy of any rule to drift)
# ---------------------------------------------------------------------------


def _formality_item_score(
    item: WardrobeItemInput, occasion_formality: int, tolerance: int
) -> float:
    if item.category is None:
        return 0.5
    item_formality = CATEGORY_FORMALITY[item.category]
    distance = abs(item_formality - occasion_formality)
    if distance <= tolerance:
        return 1.0
    over = distance - tolerance
    return max(0.0, 1.0 - over / 5.0)


def _recency_item_score(item: WardrobeItemInput, as_of: date) -> float:
    """Favours under-worn items -- wear_count/last_worn_at vs as_of. Also
    the cost_per_wear hook shipped in SS-015."""
    wear_count_score = 1.0 / (1.0 + max(0, item.wear_count))
    if item.last_worn_at is None:
        days_score = 1.0
    else:
        days_since = max(0, (as_of - item.last_worn_at).days)
        days_score = min(1.0, days_since / 90.0)
    return (wear_count_score + days_score) / 2.0


def _season_item_score(item: WardrobeItemInput, season: SeasonTag | None) -> float:
    if season is None:
        return 1.0
    if not item.season_tags:
        return 0.6  # unknown -- mild neutral, never a hard exclusion
    if season in item.season_tags or "all" in item.season_tags:
        return 1.0
    return 0.3


def _occasion_tag_item_score(item: WardrobeItemInput, occasion_key: str) -> float:
    """Additive-only, never gating -- an item with no matching occasion tag
    still contributes to formality_fit etc; this rule alone never excludes a
    candidate (weight is only 0.10)."""
    return 1.0 if occasion_key in item.occasion_tags else 0.0


def _style_preference_item_bonus(
    item: WardrobeItemInput, style_preferences: StylePreferencesInput | None
) -> float:
    """``style_preferences: null`` -> contributes 0, never raises, never
    omitted from the weighted sum (the total still sums correctly over the
    same fixed weights)."""
    if style_preferences is None or item.color_primary is None:
        return 0.0
    favourites = style_preferences.favourite_colours or []
    for fav_hex in favourites:
        if _hue_distance_score(item.color_primary, fav_hex) >= 0.85:
            return 1.0
    return 0.0


def _category_completeness_score(
    items: list[WardrobeItemInput], rules: StylingRulesOverride
) -> float:
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


def _colour_harmony_score(items: list[WardrobeItemInput]) -> float:
    colored = [item.color_primary for item in items if item.color_primary is not None]
    if len(colored) < 2:
        return 1.0  # nothing to clash with
    base_color = colored[0]
    scores = [_hue_distance_score(base_color, other) for other in colored[1:]]
    return _mean(scores, default=1.0)


# ---------------------------------------------------------------------------
# Internal: colour (hex -> HSV, deterministic)
#
# [inference -- a deliberately simple, tunable v1 heuristic, not a verified
# colour-theory standard. Real quality validation is BL-077's scope.]
# ---------------------------------------------------------------------------


def _hex_to_hsv(hex_color: str) -> tuple[float, float, float] | None:
    """Never raises -- an unparsable hex string returns ``None`` so callers
    can degrade gracefully rather than crash the whole pre-filter on one bad
    colour value."""
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        r = int(value[0:2], 16) / 255.0
        g = int(value[2:4], 16) / 255.0
        b = int(value[4:6], 16) / 255.0
    except ValueError:
        return None
    return colorsys.rgb_to_hsv(r, g, b)


def _is_near_white(hex_color: str) -> bool:
    """The "white-dominant" test:
    ``value >= NEAR_WHITE_VALUE_THRESHOLD and saturation <= NEAR_WHITE_SATURATION_THRESHOLD``."""
    hsv = _hex_to_hsv(hex_color)
    if hsv is None:
        return False
    _, saturation, value = hsv
    return value >= NEAR_WHITE_VALUE_THRESHOLD and saturation <= NEAR_WHITE_SATURATION_THRESHOLD


def _item_is_hard_excluded_white(item: WardrobeItemInput) -> bool:
    """Fails CLOSED, not open (SS-037): an item whose colour cannot be
    parsed as 3/6-digit hex -- a named colour such as "white", "off
    white", "ivory", or any other unparsable string -- is excluded
    rather than silently passed through. This function is only ever
    called when the occasion already applies a hard colour exclusion
    (see generate_candidates's "white" in effective_excluded gate), so
    an unknown colour here means "cannot rule out white," not "assume
    not white." A hex colour is still excluded only by the real
    near-white HSV test."""
    if item.color_primary is None:
        return False
    if _hex_to_hsv(item.color_primary) is None:
        return True
    return _is_near_white(item.color_primary)


def _hue_distance_score(hex_a: str, hex_b: str) -> float:
    """A colour is "neutral" (harmonizes with anything, score 1.0) if
    ``saturation <= NEAR_WHITE_SATURATION_THRESHOLD`` (near-grey/black/white
    -- reuses the saturation cut but not the value cut, since near-black is
    also neutral). Otherwise, hue distance (mod 360, folded to <=180) between
    the two colours: <=30 deg (analogous) -> 0.9; 30-60 -> 0.6; 60-150
    (clashing midrange) -> 0.5; 150-180 (complementary/contrast,
    fashion-conventional) -> 0.85."""
    hsv_a = _hex_to_hsv(hex_a)
    hsv_b = _hex_to_hsv(hex_b)
    if hsv_a is None or hsv_b is None:
        return 0.75  # unparsable input -- neutral fallback, never crash
    hue_a, sat_a, _ = hsv_a
    hue_b, sat_b, _ = hsv_b
    if sat_a <= NEAR_WHITE_SATURATION_THRESHOLD or sat_b <= NEAR_WHITE_SATURATION_THRESHOLD:
        return 1.0
    diff_deg = abs(hue_a - hue_b) * 360.0
    diff_deg = min(diff_deg, 360.0 - diff_deg)
    if diff_deg <= 30:
        return 0.9
    if diff_deg <= 60:
        return 0.6
    if diff_deg <= 150:
        return 0.5
    return 0.85


# ---------------------------------------------------------------------------
# Internal: small numeric helpers
# ---------------------------------------------------------------------------


def _mean(values: list[float], *, default: float) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
