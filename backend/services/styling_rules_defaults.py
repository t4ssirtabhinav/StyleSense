"""Single source of truth for every numeric/tunable constant SS-027's
styling rules engine uses.

**All of the following are Architect-assigned starting values, not verified
product/stylist input** -- flagged once here, not per-line (see
``docs/tickets/SS-027-design.md``'s "Concrete values to use, not invent"
section). Colour-harmony and formality-distance scoring are v1 heuristics;
real quality validation is tracked by ``BL-077`` (Epic 3's unrun AI eval),
not this ticket's job.
"""

from __future__ import annotations

from typing import get_args

from ai.ports.interfaces import WardrobeCategory
from services.styling_rules_types import OccasionKind, StylingRulesOverride

# ---------------------------------------------------------------------------
# Category -> slot / formality
# ---------------------------------------------------------------------------

# A dict covering all 21 WardrobeCategory members, not a function with a
# fallback -- a missing key must be a loud KeyError a test catches, never a
# silent default (see test_styling_rules_defaults.py).
CATEGORY_SLOT: dict[WardrobeCategory, str] = {
    "western_top": "top",
    "ethnic_kurta": "top",
    "western_bottom": "bottom",
    "western_dress": "one_piece",
    "ethnic_saree": "one_piece",
    "ethnic_lehenga": "one_piece",
    "ethnic_anarkali": "one_piece",
    "ethnic_salwar_kameez": "one_piece",
    "ethnic_sherwani": "one_piece",
    "indo_western": "one_piece",
    "western_outerwear": "outerwear",
    "footwear_formal": "footwear",
    "footwear_casual": "footwear",
    "footwear_ethnic": "footwear",
    "footwear_sports": "footwear",
    "accessory_bag": "accessory",
    "accessory_jewellery": "accessory",
    "accessory_watch": "accessory",
    "accessory_belt": "accessory",
    "accessory_scarf": "accessory",
    "ethnic_dupatta": "accessory",
}

# 0-10 scale, matching occasions.formality's own scale -- an Architect
# inference, not sourced from anywhere.
CATEGORY_FORMALITY: dict[WardrobeCategory, int] = {
    "western_top": 3,
    "western_bottom": 3,
    "western_dress": 5,
    "western_outerwear": 4,
    "ethnic_kurta": 5,
    "ethnic_saree": 8,
    "ethnic_lehenga": 9,
    "ethnic_anarkali": 8,
    "ethnic_salwar_kameez": 6,
    "ethnic_dupatta": 5,
    "ethnic_sherwani": 9,
    "indo_western": 6,
    "footwear_formal": 7,
    "footwear_casual": 3,
    "footwear_ethnic": 6,
    "footwear_sports": 1,
    "accessory_bag": 4,
    "accessory_jewellery": 5,
    "accessory_watch": 4,
    "accessory_belt": 3,
    "accessory_scarf": 3,
}

# Fails loudly at import time (not silently) if CATEGORY_SLOT / CATEGORY_FORMALITY
# ever drift from the real WardrobeCategory Literal.
_WARDROBE_CATEGORIES: tuple[str, ...] = get_args(WardrobeCategory)
assert set(CATEGORY_SLOT) == set(_WARDROBE_CATEGORIES), (
    "CATEGORY_SLOT must cover every WardrobeCategory member exactly"
)
assert set(CATEGORY_FORMALITY) == set(_WARDROBE_CATEGORIES), (
    "CATEGORY_FORMALITY must cover every WardrobeCategory member exactly"
)

# ---------------------------------------------------------------------------
# Occasion kind -> default styling rules
# ---------------------------------------------------------------------------

# A literal, exhaustive dict over the 9 `kind` values -- not a function, so a
# missing kind is a KeyError at import time / a test failure, not a silent
# runtime default.
DEFAULT_STYLING_RULES_BY_KIND: dict[str, StylingRulesOverride] = {
    "everyday": StylingRulesOverride(
        required_base="either", footwear_required=True, formality_tolerance=3
    ),
    "travel": StylingRulesOverride(
        required_base="either", footwear_required=True, formality_tolerance=3
    ),
    "social": StylingRulesOverride(
        required_base="either", footwear_required=True, formality_tolerance=3
    ),
    "milestone": StylingRulesOverride(
        required_base="either", footwear_required=True, formality_tolerance=3
    ),
    "professional": StylingRulesOverride(
        required_base="either",
        footwear_required=True,
        preferred_footwear_categories=["footwear_formal"],
        formality_tolerance=1,
    ),
    "sport": StylingRulesOverride(
        required_base="either",
        footwear_required=True,
        preferred_footwear_categories=["footwear_sports"],
        formality_tolerance=2,
    ),
    "ceremony": StylingRulesOverride(
        required_base="either",
        footwear_required=True,
        preferred_footwear_categories=["footwear_ethnic", "footwear_formal"],
        preferred_accessory_categories=["accessory_jewellery"],
        formality_tolerance=1,
    ),
    "festival": StylingRulesOverride(
        required_base="either",
        footwear_required=True,
        preferred_footwear_categories=["footwear_ethnic", "footwear_formal"],
        preferred_accessory_categories=["accessory_jewellery"],
        formality_tolerance=1,
    ),
    "religious": StylingRulesOverride(
        required_base="either",
        footwear_required=True,
        preferred_footwear_categories=["footwear_ethnic", "footwear_formal"],
        preferred_accessory_categories=["accessory_jewellery"],
        formality_tolerance=1,
    ),
}

_OCCASION_KINDS: tuple[str, ...] = get_args(OccasionKind)
assert set(DEFAULT_STYLING_RULES_BY_KIND) == set(_OCCASION_KINDS), (
    "DEFAULT_STYLING_RULES_BY_KIND must cover every occasions.kind CHECK value exactly"
)


def default_styling_rules_for(kind: str) -> StylingRulesOverride:
    """Thin lookup into ``DEFAULT_STYLING_RULES_BY_KIND`` -- not a
    re-derivation. Used whenever ``OccasionStylingInput.styling_rules`` is
    ``{}`` or fails to parse into ``StylingRulesOverride``. Raises
    ``KeyError`` for an unrecognized kind (loud by design -- see module
    docstring)."""
    return DEFAULT_STYLING_RULES_BY_KIND[kind]


# ---------------------------------------------------------------------------
# wedding_guest white-exclusion -- code-level, unconditional guard
# ---------------------------------------------------------------------------

# Code-level, unconditional, applied regardless of what styling_rules
# contains or omits. This is the literal mechanism for the AC's "enforced in
# code, not in a prompt" -- checked in styling_rules_engine.py IN ADDITION TO
# (never instead of) whatever excluded_color_families a fetched
# StylingRulesOverride supplies. Keyed by exact occasion key, not by `kind`
# -- see design doc's Edge Cases for why (deliberate belt-and-suspenders for
# the one occasion CLAUDE.md itself names verbatim, not a template for every
# future colour exclusion).
HARD_EXCLUDED_COLOR_FAMILIES: dict[str, frozenset[str]] = {
    "wedding_guest": frozenset({"white"}),
}

# ---------------------------------------------------------------------------
# Colour harmony thresholds (HSV, 0-1 scale)
# ---------------------------------------------------------------------------

# The "white-dominant" test: a hex colour is near-white if
# value >= NEAR_WHITE_VALUE_THRESHOLD and saturation <= NEAR_WHITE_SATURATION_THRESHOLD.
# Both numbers are an inference, not a verified colour-science standard --
# tunable without touching call sites.
NEAR_WHITE_VALUE_THRESHOLD = 0.92
NEAR_WHITE_SATURATION_THRESHOLD = 0.12

# ---------------------------------------------------------------------------
# Combinatorics bound
# ---------------------------------------------------------------------------

# The per-slot cap that bounds combinatorics regardless of wardrobe size --
# see styling_rules_engine.py's module docstring for the worked-out bound.
MAX_ITEMS_PER_SLOT = 8

# ---------------------------------------------------------------------------
# Rule weights (sum to 1.0)
# ---------------------------------------------------------------------------

# style_preferences is folded into wear_recency's sibling contribution (see
# styling_rules_engine.py), not a 7th weight, to keep the sum simple and
# auditable.
RULE_WEIGHTS: dict[str, float] = {
    "formality_fit": 0.30,
    "category_completeness": 0.20,
    "colour_harmony": 0.20,
    "wear_recency": 0.15,
    "occasion_tag_bonus": 0.10,
    "season_fit": 0.05,
}

assert abs(sum(RULE_WEIGHTS.values()) - 1.0) < 1e-9, "RULE_WEIGHTS must sum to 1.0"
