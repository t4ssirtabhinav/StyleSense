"""SS-038 -- the one colour-primitives module both stage① (eligibility's
near-white guard) and stage③ (attribute scoring's pairwise colour harmony)
depend on, so there is exactly one implementation, never two.

``hex_to_hsv``/``hue_distance_score``/``is_near_white``/
``item_is_hard_excluded_white`` are moved verbatim from
``styling_rules_engine.py``'s former ``_hex_to_hsv``/``_hue_distance_score``/
``_is_near_white``/``_item_is_hard_excluded_white`` -- same formulas, same
fail-closed semantics. ``hue_distance_score``'s flat ``0.75`` fallback for
unparsable input is DELIBERATELY unchanged (``BL-128``'s fallback half stays
open -- needs ``BL-064``/``BL-079``'s hex-to-colour-family binning first).

``is_near_white``/``item_is_hard_excluded_white`` are now parameterized on
thresholds instead of importing module constants, so the eligibility stage
can pass the ``app_config``/occasion-resolved values through (resolves
``BL-111``).

``pairwise_colour_harmony`` is NEW -- replaces ``_colour_harmony_score``'s
star-topology (everything compared to ``colored[0]``, order-dependent) with
every ``itertools.combinations(colored, 2)`` pair, mean of all pairs
(resolves ``BL-128``'s star-topology half).
"""

from __future__ import annotations

import colorsys
import itertools

from services.styling_rules_defaults import (
    NEAR_WHITE_SATURATION_THRESHOLD as _NEAR_WHITE_SATURATION_THRESHOLD_DEFAULT,
)
from services.styling_rules_types import WardrobeItemInput

__all__ = [
    "hex_to_hsv",
    "hue_distance_score",
    "is_near_white",
    "item_is_hard_excluded_white",
    "pairwise_colour_harmony",
]

# hue_distance_score's own "neutral" cut re-uses the SATURATION half of the
# near-white test (near-grey/black/white all harmonize with anything) but
# NOT the value half (near-black is also neutral, near-white is not the
# point here) -- moved verbatim from styling_rules_engine._hue_distance_score,
# which imported NEAR_WHITE_SATURATION_THRESHOLD as a fixed module constant.
# This is deliberately NOT parameterized (unlike is_near_white/
# item_is_hard_excluded_white below): hue_distance_score's neutral-colour cut
# is a general colour-harmony heuristic, not the occasion-specific
# near-white HARD EXCLUSION this ticket moves to app_config -- conflating the
# two would make a wedding_guest override narrow general colour-harmony
# scoring everywhere too, which nothing in the design asks for.
_HUE_NEUTRAL_SATURATION_CUTOFF = _NEAR_WHITE_SATURATION_THRESHOLD_DEFAULT


def hex_to_hsv(hex_color: str) -> tuple[float, float, float] | None:
    """Never raises -- an unparsable hex string returns ``None`` so callers
    can degrade gracefully rather than crash the whole pipeline on one bad
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


def hue_distance_score(hex_a: str, hex_b: str) -> float:
    """A colour is "neutral" (harmonizes with anything, score 1.0) if
    ``saturation <= _HUE_NEUTRAL_SATURATION_CUTOFF`` (near-grey/black/white).
    Otherwise, hue distance (mod 360, folded to <=180) between the two
    colours: <=30 deg (analogous) -> 0.9; 30-60 -> 0.6; 60-150 (clashing
    midrange) -> 0.5; 150-180 (complementary/contrast, fashion-conventional)
    -> 0.85.

    Unparsable input -> 0.75 flat fallback, DELIBERATELY UNCHANGED from
    SS-027/037 (see module docstring -- BL-128's fallback half stays open)."""
    hsv_a = hex_to_hsv(hex_a)
    hsv_b = hex_to_hsv(hex_b)
    if hsv_a is None or hsv_b is None:
        return 0.75  # unparsable input -- neutral fallback, never crash
    hue_a, sat_a, _ = hsv_a
    hue_b, sat_b, _ = hsv_b
    if sat_a <= _HUE_NEUTRAL_SATURATION_CUTOFF or sat_b <= _HUE_NEUTRAL_SATURATION_CUTOFF:
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


def is_near_white(hex_color: str, *, value_threshold: float, saturation_threshold: float) -> bool:
    """The "white-dominant" test: ``value >= value_threshold and saturation
    <= saturation_threshold``. Same predicate as SS-027/037's
    ``_is_near_white``, now parameterized so the eligibility stage can pass
    the app_config/occasion-resolved thresholds through."""
    hsv = hex_to_hsv(hex_color)
    if hsv is None:
        return False
    _, saturation, value = hsv
    return value >= value_threshold and saturation <= saturation_threshold


def item_is_hard_excluded_white(
    item: WardrobeItemInput, *, value_threshold: float, saturation_threshold: float
) -> bool:
    """Fails CLOSED, not open (SS-037): an item whose colour cannot be
    parsed as 3/6-digit hex -- a named colour such as "white", "off white",
    "ivory", or any other unparsable string -- is excluded rather than
    silently passed through. Only ever called when the occasion already
    applies a hard colour exclusion, so an unknown colour here means "cannot
    rule out white," not "assume not white." A hex colour is still excluded
    only by the real near-white HSV test."""
    if item.color_primary is None:
        return False
    if hex_to_hsv(item.color_primary) is None:
        return True
    return is_near_white(
        item.color_primary, value_threshold=value_threshold, saturation_threshold=saturation_threshold
    )


def pairwise_colour_harmony(items: list[WardrobeItemInput]) -> float:
    """Replaces ``_colour_harmony_score``'s star-topology (everything
    compared to ``colored[0]``, order-dependent) with every
    ``itertools.combinations(colored, 2)`` pair, mean of all pairs. Same
    ``<2 colours -> 1.0`` "nothing to clash with" base case as v0 (a
    ``one_piece`` base has exactly one item, so this is always ``1.0``
    there, consistent with today)."""
    colored = [item.color_primary for item in items if item.color_primary is not None]
    if len(colored) < 2:
        return 1.0  # nothing to clash with
    scores = [hue_distance_score(a, b) for a, b in itertools.combinations(colored, 2)]
    return sum(scores) / len(scores)
