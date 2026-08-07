"""Tests for backend/services/engine_v2_eligibility.py (SS-038)."""

from __future__ import annotations

from services.app_config import AppConfigSnapshot
from services.app_config_specs import NearWhiteThresholdConfig
from services.engine_v2_eligibility import (
    filter_eligible,
    resolve_near_white_thresholds,
    resolve_styling_rules,
)
from services.styling_rules_types import (
    OccasionStylingInput,
    StylingRulesOverride,
    WardrobeItemInput,
)


def _item(
    id: str,
    *,
    category: str | None = "ethnic_saree",
    color: str | None = "#8B0000",
) -> WardrobeItemInput:
    return WardrobeItemInput(id=id, category=category, color_primary=color)  # type: ignore[arg-type]


def _occasion(
    *, key: str = "office", kind: str = "professional", formality: int = 6, styling_rules: dict | None = None
) -> OccasionStylingInput:
    return OccasionStylingInput(
        key=key, kind=kind, formality=formality, styling_rules=styling_rules or {}  # type: ignore[arg-type]
    )


def _empty_snapshot() -> AppConfigSnapshot:
    return AppConfigSnapshot(values={}, fetched_at=0.0, stale=False)


def _snapshot_with(value: dict) -> AppConfigSnapshot:
    return AppConfigSnapshot(
        values={"near_white_threshold": value}, fetched_at=0.0, stale=False
    )


# ---------------------------------------------------------------------------
# resolve_near_white_thresholds
# ---------------------------------------------------------------------------


def test_resolve_near_white_thresholds_coded_default_when_snapshot_empty() -> None:
    rules = resolve_styling_rules(_occasion())
    result = resolve_near_white_thresholds(_empty_snapshot(), rules)
    assert result.value_threshold == 0.92
    assert result.saturation_threshold == 0.12


def test_resolve_near_white_thresholds_uses_app_config_value_when_present() -> None:
    rules = resolve_styling_rules(_occasion())
    snapshot = _snapshot_with({"value_threshold": 0.80, "saturation_threshold": 0.20})
    result = resolve_near_white_thresholds(snapshot, rules)
    assert result.value_threshold == 0.80
    assert result.saturation_threshold == 0.20


def test_resolve_near_white_thresholds_occasion_override_wins() -> None:
    occasion = _occasion(
        key="wedding_guest_narrow",
        kind="ceremony",
        formality=9,
        styling_rules={"near_white_value_threshold": 0.99, "near_white_saturation_threshold": 0.02},
    )
    rules = resolve_styling_rules(occasion)
    snapshot = _snapshot_with({"value_threshold": 0.80, "saturation_threshold": 0.20})
    result = resolve_near_white_thresholds(snapshot, rules)
    assert result.value_threshold == 0.99
    assert result.saturation_threshold == 0.02


def test_resolve_near_white_thresholds_different_occasion_key_unaffected() -> None:
    """A different occasion sharing the same `kind` is NOT automatically
    affected by another occasion's override (BL-111's edge case, asserted
    literally)."""
    narrowed_occasion = _occasion(
        key="wedding_guest",
        kind="ceremony",
        formality=9,
        styling_rules={"near_white_value_threshold": 0.99},
    )
    other_occasion = _occasion(key="formal_event", kind="ceremony", formality=8)

    snapshot = _snapshot_with({"value_threshold": 0.92, "saturation_threshold": 0.12})

    narrowed_rules = resolve_styling_rules(narrowed_occasion)
    other_rules = resolve_styling_rules(other_occasion)

    narrowed_result = resolve_near_white_thresholds(snapshot, narrowed_rules)
    other_result = resolve_near_white_thresholds(snapshot, other_rules)

    assert narrowed_result.value_threshold == 0.99
    assert other_result.value_threshold == 0.92  # unaffected by the other occasion's override


def test_resolve_near_white_thresholds_partial_override_only_one_field() -> None:
    occasion = _occasion(
        key="test_partial",
        kind="everyday",
        formality=5,
        styling_rules={"near_white_value_threshold": 0.99},
    )
    rules = resolve_styling_rules(occasion)
    snapshot = _snapshot_with({"value_threshold": 0.80, "saturation_threshold": 0.20})
    result = resolve_near_white_thresholds(snapshot, rules)
    assert result.value_threshold == 0.99  # overridden
    assert result.saturation_threshold == 0.20  # falls back to app_config, not the coded default


def test_resolve_near_white_thresholds_malformed_row_degrades_to_coded_default() -> None:
    rules = resolve_styling_rules(_occasion())
    malformed_snapshot = AppConfigSnapshot(
        values={"near_white_threshold": {"value_threshold": "not-a-number"}},
        fetched_at=0.0,
        stale=False,
    )
    result = resolve_near_white_thresholds(malformed_snapshot, rules)
    assert result.value_threshold == 0.92
    assert result.saturation_threshold == 0.12


# ---------------------------------------------------------------------------
# filter_eligible -- reproduces wedding_guest's 100% near-white exclusion
# ---------------------------------------------------------------------------


def test_filter_eligible_wedding_guest_excludes_all_near_white_with_coded_default() -> None:
    wardrobe = [
        _item("saree1", category="ethnic_saree", color="#FFFFFF"),
        _item("saree2", category="ethnic_saree", color="#FFFEFE"),
        _item("shoe1", category="footwear_ethnic", color="#8B0000"),
    ]
    occasion = _occasion(key="wedding_guest", kind="ceremony", formality=9)
    rules = resolve_styling_rules(occasion)
    near_white = NearWhiteThresholdConfig()  # coded default, config row absent

    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=near_white)

    eligible_ids = {item.id for item in result.eligible_items}
    assert "saree1" not in eligible_ids
    assert "saree2" not in eligible_ids
    assert "shoe1" in eligible_ids


def test_filter_eligible_non_wedding_occasion_allows_white() -> None:
    wardrobe = [_item("saree1", category="ethnic_saree", color="#FFFFFF")]
    occasion = _occasion(key="office", kind="professional", formality=6)
    rules = resolve_styling_rules(occasion)
    near_white = NearWhiteThresholdConfig()

    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=near_white)
    assert "saree1" in {item.id for item in result.eligible_items}


def test_filter_eligible_dedupes_and_counts_missing_fields() -> None:
    wardrobe = [
        _item("dup", category="ethnic_saree", color="#8B0000"),
        _item("dup", category="ethnic_saree", color="#8B0000"),
        _item("no_category", category=None, color="#8B0000"),
        _item("no_color", category="ethnic_saree", color=None),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    near_white = NearWhiteThresholdConfig()

    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=near_white)
    assert len(result.eligible_items) == 1
    assert result.excluded_missing_color_or_category == 2


# ---------------------------------------------------------------------------
# resolve_styling_rules -- moved verbatim, sanity check
# ---------------------------------------------------------------------------


def test_resolve_styling_rules_degrades_to_kind_default_on_empty() -> None:
    occasion = _occasion(key="new_occasion", kind="everyday", formality=5, styling_rules={})
    resolved = resolve_styling_rules(occasion)
    assert resolved.required_base == "either"
    assert resolved.footwear_required is True


def test_resolve_styling_rules_malformed_field_drops_to_kind_default() -> None:
    occasion = _occasion(
        key="test_malformed", kind="everyday", formality=5, styling_rules={"required_base": 12345}
    )
    resolved = resolve_styling_rules(occasion)
    assert resolved.required_base == "either"


def test_resolve_styling_rules_returns_stylingrulesoverride_type() -> None:
    resolved = resolve_styling_rules(_occasion())
    assert isinstance(resolved, StylingRulesOverride)
