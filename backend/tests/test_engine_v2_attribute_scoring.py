"""Tests for backend/services/engine_v2_attribute_scoring.py (SS-038)."""

from __future__ import annotations

from datetime import date

from adapters.interfaces import FabricAttributes
from services.engine_v2_attribute_scoring import (
    fabric_weather_score,
    register_coherence_score,
    score_assembled_candidate,
    volume_balance_score,
)
from services.engine_v2_eligibility import resolve_styling_rules
from services.engine_v2_types import AssembledCandidate, GarmentAttributes, NoveltyInputs
from services.styling_rules_defaults import ENGINE_V2_RULE_WEIGHTS
from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput

_AS_OF = date(2026, 7, 29)


def _item(
    id: str, *, category: str = "ethnic_kurta", color: str = "#8B0000", fabric: str | None = None
) -> WardrobeItemInput:
    """``category`` is always a real (21-value) ``WardrobeCategory`` member --
    ``WardrobeItemInput.category`` is a strict Pydantic ``Literal``, it
    rejects synthetic ``garment_types``-shaped strings like ``"kurta"``
    outright. Per the design doc's own "Open questions" #4, these unit
    tests exercise the ``garment_lookup``-hit branch by having the FAKE
    ``garment_lookup`` respond to a real enum value AS IF it resolved
    through the registry -- the returned ``GarmentAttributes.key`` need not
    match the enum name itself."""
    return WardrobeItemInput(id=id, category=category, color_primary=color, fabric=fabric)  # type: ignore[arg-type]


def _occasion(*, key: str = "office", kind: str = "professional", formality: int = 6) -> OccasionStylingInput:
    return OccasionStylingInput(key=key, kind=kind, formality=formality)  # type: ignore[arg-type]


def _attrs(
    key: str,
    *,
    register: tuple[str, ...] = ("ethnic",),
    pairs_with: tuple[str, ...] = (),
    volume_class: str | None = None,
) -> GarmentAttributes:
    return GarmentAttributes(
        key=key,
        assembly_slot="top",
        garment_slot="torso_base",
        layer=0,
        register=register,
        base_formality=4,
        pairs_with=pairs_with,
        requires_with=(),
        excludes_with=(),
        volume_class=volume_class,
    )


# ---------------------------------------------------------------------------
# volume_balance_score
# ---------------------------------------------------------------------------


def test_volume_balance_score_penalizes_two_voluminous_non_streetwear() -> None:
    a = _item("a")
    b = _item("b")
    a_attrs = _attrs("a", register=("ethnic",), volume_class="voluminous")
    b_attrs = _attrs("b", register=("ethnic",), volume_class="oversized")

    def real_lookup(category: str) -> GarmentAttributes | None:
        return a_attrs if category == a.category else b_attrs

    score = volume_balance_score([a, b], real_lookup)
    assert score == 0.6


def test_volume_balance_score_high_when_streetwear_register() -> None:
    a = _item("a")
    b = _item("b")
    a_attrs = _attrs("a", register=("streetwear",), volume_class="voluminous")
    b_attrs = _attrs("b", register=("streetwear",), volume_class="oversized")

    def real_lookup(category: str) -> GarmentAttributes | None:
        return a_attrs if category == a.category else b_attrs

    score = volume_balance_score([a, b], real_lookup)
    assert score == 1.0


def test_volume_balance_score_unresolved_item_is_neutral() -> None:
    a = _item("a")
    b = _item("b")

    def real_lookup(category: str) -> GarmentAttributes | None:
        return None  # everything unresolved

    score = volume_balance_score([a, b], real_lookup)
    assert score == 1.0


def test_volume_balance_score_missing_volume_class_is_neutral() -> None:
    a = _item("a")
    b = _item("b")
    a_attrs = _attrs("a", volume_class=None)
    b_attrs = _attrs("b", volume_class="voluminous")

    def real_lookup(category: str) -> GarmentAttributes | None:
        return a_attrs if category == a.category else b_attrs

    score = volume_balance_score([a, b], real_lookup)
    assert score == 1.0  # no signal for this pair -- a.volume_class is None


# ---------------------------------------------------------------------------
# register_coherence_score
# ---------------------------------------------------------------------------


def test_register_coherence_high_when_registers_overlap() -> None:
    a = _item("a")
    b = _item("b")
    a_attrs = _attrs("a", register=("ethnic", "festive"))
    b_attrs = _attrs("b", register=("ethnic",))

    def real_lookup(category: str) -> GarmentAttributes | None:
        return a_attrs if category == a.category else b_attrs

    assert register_coherence_score([a, b], real_lookup) == 1.0


def test_register_coherence_high_when_pairs_with_match() -> None:
    a = _item("a", category="ethnic_kurta")
    b = _item("b", category="western_bottom")
    a_attrs = _attrs("kurta", register=("ethnic",), pairs_with=("palazzo",))
    b_attrs = _attrs("palazzo", register=("indo_western",))

    def real_lookup(category: str) -> GarmentAttributes | None:
        return a_attrs if category == "ethnic_kurta" else b_attrs

    assert register_coherence_score([a, b], real_lookup) == 1.0


def test_register_coherence_low_when_conflicting_registers() -> None:
    a = _item("a", category="ethnic_kurta")
    b = _item("b", category="western_bottom")
    a_attrs = _attrs("kurta", register=("ethnic",))
    b_attrs = _attrs("joggers", register=("athleisure",))

    def real_lookup(category: str) -> GarmentAttributes | None:
        return a_attrs if category == "ethnic_kurta" else b_attrs

    assert register_coherence_score([a, b], real_lookup) == 0.5


def test_register_coherence_unresolved_pair_is_neutral() -> None:
    a = _item("a")
    b = _item("b")

    def real_lookup(category: str) -> GarmentAttributes | None:
        return None

    assert register_coherence_score([a, b], real_lookup) == 1.0


# ---------------------------------------------------------------------------
# fabric_weather_score -- BL-125's per-sub-signal gate
# ---------------------------------------------------------------------------

_FABRIC_ATTRS = {
    "silk": FabricAttributes(key="silk", weight="medium", breathability=5, season_affinity=None),
    "khadi": FabricAttributes(key="khadi", weight="light", breathability=9, season_affinity=None),
    "cotton": FabricAttributes(key="cotton", weight="light", breathability=9, season_affinity=("summer",)),
    "wool": FabricAttributes(key="wool", weight="heavy", breathability=1, season_affinity=("winter",)),
}


def test_fabric_weather_score_season_none_is_no_opinion() -> None:
    item = _item("i1", fabric="cotton")
    assert fabric_weather_score([item], _FABRIC_ATTRS, season=None) == 1.0


def test_fabric_weather_score_no_fabric_row_is_no_opinion() -> None:
    item = _item("i1", fabric="unknown_fabric_slug")
    assert fabric_weather_score([item], _FABRIC_ATTRS, season="summer") == 1.0


def test_fabric_weather_score_no_populated_fabric_anywhere_is_1() -> None:
    item = _item("i1", fabric=None)
    assert fabric_weather_score([item], _FABRIC_ATTRS, season="summer") == 1.0


def test_fabric_weather_score_silk_khadi_season_signal_skipped_but_breathability_contributes() -> None:
    """BL-125's decided gate: season_affinity IS NULL (silk, khadi) skips
    ONLY that sub-signal; breathability still contributes."""
    silk_item = _item("silk_item", fabric="silk")
    khadi_item = _item("khadi_item", fabric="khadi")

    silk_summer_score = fabric_weather_score([silk_item], _FABRIC_ATTRS, season="summer")
    khadi_summer_score = fabric_weather_score([khadi_item], _FABRIC_ATTRS, season="summer")

    # Both fabrics have HIGH breathability (5, 9) -- summer favours high
    # breathability, so despite season_affinity=None, the score should NOT
    # collapse to the flat neutral 1.0 caused by "no signal at all" --
    # unless breathability alone already computes to 1.0, in which case we
    # instead assert it differs from a LOW-breathability winter-only fabric
    # to prove the breathability sub-signal is genuinely live.
    wool_item = _item("wool_item", fabric="wool")
    wool_summer_score = fabric_weather_score([wool_item], _FABRIC_ATTRS, season="summer")
    assert silk_summer_score != wool_summer_score
    assert khadi_summer_score != wool_summer_score


def test_fabric_weather_score_populated_season_affinity_match_scores_high() -> None:
    item = _item("i1", fabric="cotton")
    score = fabric_weather_score([item], _FABRIC_ATTRS, season="summer")
    assert score > 0.5


def test_fabric_weather_score_populated_season_affinity_mismatch_scores_lower() -> None:
    item = _item("i1", fabric="wool")
    score = fabric_weather_score([item], _FABRIC_ATTRS, season="summer")
    matching_score = fabric_weather_score([item], _FABRIC_ATTRS, season="winter")
    assert score < matching_score


# ---------------------------------------------------------------------------
# score_assembled_candidate -- shape and integration
# ---------------------------------------------------------------------------


def test_score_assembled_candidate_rule_scores_match_engine_v2_weights_exactly() -> None:
    candidate = AssembledCandidate(
        items=[_item("a", category="western_top"), _item("b", category="western_bottom")],
        gap_flags=[],
    )
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    scored = score_assembled_candidate(
        candidate,
        occasion,
        rules,
        garment_lookup=lambda c: None,
        fabric_attrs={},
        novelty_inputs=NoveltyInputs(),
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    rule_names = {r.rule for r in scored.rule_scores}
    assert rule_names == set(ENGINE_V2_RULE_WEIGHTS)
    assert 0.0 <= scored.total_score <= 1.0
    assert scored.item_ids == ["a", "b"]


def test_score_assembled_candidate_carries_gap_flags_through() -> None:
    candidate = AssembledCandidate(
        items=[_item("a", category="western_top"), _item("b", category="western_bottom")],
        gap_flags=["missing_footwear"],
    )
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    scored = score_assembled_candidate(
        candidate,
        occasion,
        rules,
        garment_lookup=lambda c: None,
        fabric_attrs={},
        novelty_inputs=NoveltyInputs(),
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert scored.gap_flags == ["missing_footwear"]
