"""Tests for backend/services/styling_rules_engine.py (SS-027)."""

from __future__ import annotations

import copy
import json
import random as _random
import time
from datetime import date, timedelta
from typing import get_args

from ai.ports.interfaces import StylePreferencesInput, WardrobeCategory
from services.styling_rules_defaults import RULE_WEIGHTS
from services.styling_rules_engine import (
    _resolve_styling_rules,
    generate_candidates,
    render_candidate_for_prompt,
    score_candidate,
)
from services.styling_rules_types import OccasionKind, OccasionStylingInput, WardrobeItemInput

_AS_OF = date(2026, 7, 29)


def _item(
    id: str,
    *,
    category: WardrobeCategory | None = "ethnic_saree",
    color: str | None = "#1E3A8A",
    occasion_tags: list[str] | None = None,
    season_tags: list[str] | None = None,
    wear_count: int = 0,
    last_worn_at: date | None = None,
) -> WardrobeItemInput:
    return WardrobeItemInput(
        id=id,
        category=category,
        color_primary=color,
        occasion_tags=occasion_tags or [],
        season_tags=season_tags or [],  # type: ignore[arg-type]
        wear_count=wear_count,
        last_worn_at=last_worn_at,
    )


def _occasion(
    *,
    key: str = "office",
    kind: str = "professional",
    formality: int = 6,
    styling_rules: dict | None = None,
) -> OccasionStylingInput:
    return OccasionStylingInput(
        key=key,
        kind=kind,  # type: ignore[arg-type]
        formality=formality,
        styling_rules=styling_rules or {},
    )


_CATEGORIES: tuple[WardrobeCategory, ...] = get_args(WardrobeCategory)
_COLORS = ["#1E3A8A", "#8B0000", "#FFFFFF", "#228B22", "#DAA520", "#4B0082", "#FF69B4", "#000000"]


def _build_synthetic_wardrobe(
    n: int, *, seed: int = 42, as_of: date = _AS_OF
) -> list[WardrobeItemInput]:
    """Deterministic pseudo-random synthetic wardrobe -- never None
    category/color, so it always exercises real combinatorics."""
    rng = _random.Random(seed)
    items = []
    for i in range(n):
        category = _CATEGORIES[i % len(_CATEGORIES)]
        color = _COLORS[rng.randrange(len(_COLORS))]
        items.append(
            _item(
                f"item-{i}",
                category=category,
                color=color,
                occasion_tags=["office"] if i % 3 == 0 else [],
                season_tags=["summer"] if i % 4 == 0 else [],
                wear_count=rng.randrange(0, 20),
                last_worn_at=as_of - timedelta(days=rng.randrange(0, 400)),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Core AC coverage
# ---------------------------------------------------------------------------


def test_empty_wardrobe_returns_empty_result_no_exception() -> None:
    result = generate_candidates([], _occasion(), as_of=_AS_OF)
    assert result.candidates == []
    assert result.limited_options is True


def test_single_one_piece_item_produces_one_gapped_candidate() -> None:
    wardrobe = [_item("i1", category="ethnic_saree", color="#8B0000")]
    result = generate_candidates(wardrobe, _occasion(), as_of=_AS_OF)
    assert len(result.candidates) == 1
    assert result.candidates[0].gap_flags == ["missing_footwear"]
    assert result.limited_options is True


def test_all_candidate_item_ids_are_subset_of_input_ids() -> None:
    """The direct proof of the ticket's headline AC ("structurally
    impossible to hallucinate an id")."""
    for size in (20, 35, 50, 80):
        wardrobe = _build_synthetic_wardrobe(size, seed=size)
        input_ids = {item.id for item in wardrobe}
        for kind in ("everyday", "professional", "ceremony", "sport"):
            occasion = _occasion(key=f"occ_{kind}_{size}", kind=kind, formality=5)
            result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
            for candidate in result.candidates:
                assert set(candidate.item_ids) <= input_ids


def test_wedding_guest_excludes_all_white_hero_candidates() -> None:
    wardrobe = [
        _item("saree1", category="ethnic_saree", color="#FFFFFF"),
        _item("saree2", category="ethnic_saree", color="#FFFEFE"),
        _item("top1", category="western_top", color="#FFFFFF"),
        _item("bottom1", category="western_bottom", color="#FFFFFF"),
        _item("shoe1", category="footwear_ethnic", color="#8B0000"),
    ]
    occasion = _occasion(key="wedding_guest", kind="ceremony", formality=9)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)

    # Zero candidates is the expected outcome (every hero item is white, so
    # no base can be assembled) -- this is the strongest possible proof of
    # the code-level guard.
    assert result.candidates == []
    # Defensive: even if a future implementation partially relaxes this,
    # no returned candidate may include a white hero item.
    hero_ids = {"saree1", "saree2", "top1", "bottom1"}
    for candidate in result.candidates:
        assert not (set(candidate.item_ids) & hero_ids)


def test_non_wedding_occasion_allows_white() -> None:
    wardrobe = [
        _item("saree1", category="ethnic_saree", color="#FFFFFF"),
        _item("saree2", category="ethnic_saree", color="#FFFEFE"),
        _item("shoe1", category="footwear_ethnic", color="#8B0000"),
    ]
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    assert len(result.candidates) > 0
    white_ids = {"saree1", "saree2"}
    assert any(set(c.item_ids) & white_ids for c in result.candidates)


def test_other_ceremony_occasion_key_still_allows_white() -> None:
    """The guard is keyed by the literal occasion key, not by
    kind='ceremony' -- a different ceremony-kind occasion must NOT inherit
    the wedding_guest protection automatically."""
    wardrobe = [
        _item("saree1", category="ethnic_saree", color="#FFFFFF"),
        _item("shoe1", category="footwear_ethnic", color="#8B0000"),
    ]
    occasion = _occasion(key="formal_event", kind="ceremony", formality=8)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    assert any("saree1" in c.item_ids for c in result.candidates)


def test_deterministic_same_input_same_output() -> None:
    wardrobe = _build_synthetic_wardrobe(30)
    wardrobe2 = copy.deepcopy(wardrobe)
    occasion = _occasion(key="office", kind="professional", formality=6)
    occasion2 = occasion.model_copy(deep=True)
    prefs = StylePreferencesInput(favourite_colours=["#1E3A8A"], gender="woman")
    prefs2 = prefs.model_copy(deep=True)

    r1 = generate_candidates(
        wardrobe, occasion, as_of=_AS_OF, season="summer", style_preferences=prefs
    )
    r2 = generate_candidates(
        wardrobe2, occasion2, as_of=_AS_OF, season="summer", style_preferences=prefs2
    )

    assert r1.model_dump() == r2.model_dump()


def test_as_of_is_never_read_from_system_clock() -> None:
    wardrobe = _build_synthetic_wardrobe(20)
    occasion = _occasion(key="office", kind="professional", formality=6)

    r1 = generate_candidates(wardrobe, occasion, as_of=date(2020, 1, 1))
    r2 = generate_candidates(wardrobe, occasion, as_of=date(2026, 7, 29))

    assert r1.model_dump() != r2.model_dump()


def test_large_wardrobe_bounded_time_and_output_size() -> None:
    wardrobe = _build_synthetic_wardrobe(500)
    occasion = _occasion(key="office", kind="professional", formality=6)

    start = time.perf_counter()
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF, max_candidates=5)
    elapsed = time.perf_counter() - start

    # Coarse regression guard, not a strict perf SLA.
    assert elapsed < 2.0
    assert len(result.candidates) <= 5


def test_fewer_than_three_valid_candidates_sets_limited_options() -> None:
    wardrobe = [
        _item("saree1", category="ethnic_saree", color="#8B0000"),
        _item("saree2", category="ethnic_saree", color="#228B22"),
    ]
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    assert len(result.candidates) == 2
    assert result.limited_options is True


def test_null_color_or_category_items_excluded_and_counted() -> None:
    wardrobe = [
        _item("ok1", category="ethnic_saree", color="#8B0000"),
        _item("ok2", category="footwear_ethnic", color="#000000"),
        _item("no_category", category=None, color="#8B0000"),
        _item("no_color", category="ethnic_saree", color=None),
    ]
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)

    assert result.gap_report.excluded_missing_color_or_category == 2
    missing_ids = {"no_category", "no_color"}
    for candidate in result.candidates:
        assert not (set(candidate.item_ids) & missing_ids)


def test_occasion_with_empty_styling_rules_uses_kind_defaults() -> None:
    """Proves the "new occasion works the moment it is inserted" edge case
    for real -- exercised over every one of the 9 kind values."""
    wardrobe = _build_synthetic_wardrobe(24)
    for kind in get_args(OccasionKind):
        occasion = _occasion(key=f"new_occasion_{kind}", kind=kind, formality=5, styling_rules={})
        result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
        assert isinstance(result.candidates, list)
        input_ids = {item.id for item in wardrobe}
        for candidate in result.candidates:
            assert set(candidate.item_ids) <= input_ids


def test_malformed_styling_rules_degrades_without_raising() -> None:
    occasion = _occasion(
        key="test_malformed",
        kind="everyday",
        formality=5,
        styling_rules={"required_base": 12345, "unknown_key": "x"},
    )
    wardrobe = _build_synthetic_wardrobe(15)

    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)  # must not raise
    assert isinstance(result.candidates, list)

    resolved = _resolve_styling_rules(occasion)
    # required_base=12345 is wrong-typed -> dropped to None -> falls back to
    # the "everyday" kind default ("either"), never propagates 12345.
    assert resolved.required_base == "either"


def test_style_preferences_none_does_not_raise_or_change_weight_sum() -> None:
    wardrobe = _build_synthetic_wardrobe(15)
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF, style_preferences=None)
    for candidate in result.candidates:
        assert 0.0 <= candidate.total_score <= 1.0

    resolved = _resolve_styling_rules(occasion)
    total, rule_scores = score_candidate(
        wardrobe[:2], occasion, resolved, as_of=_AS_OF, season=None, style_preferences=None
    )
    expected = round(sum(RULE_WEIGHTS[r.rule] * r.score for r in rule_scores), 4)
    assert abs(total - expected) < 1e-6


def test_duplicate_ids_in_wardrobe_deduped_not_double_counted() -> None:
    wardrobe = [
        _item("dup", category="ethnic_saree", color="#8B0000"),
        _item("dup", category="ethnic_saree", color="#8B0000"),
    ]
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)

    assert len(result.candidates) == 1
    assert result.gap_report.excluded_missing_color_or_category == 0


def test_render_candidate_for_prompt_is_json_serializable_and_compact() -> None:
    wardrobe = _build_synthetic_wardrobe(20)
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    assert result.candidates, "expected at least one candidate for this fixture"

    for candidate in result.candidates:
        rendered = render_candidate_for_prompt(candidate)
        serialized = json.dumps(rendered)
        json.loads(serialized)  # must round-trip without error
        # Char-count proxy (not an actual tokenizer count) for the ticket's
        # own ~800-token-for-5-candidates [ESTIMATE] budget.
        assert len(serialized) < 600


def test_occasion_tag_mismatch_does_not_exclude_candidate() -> None:
    """occasion_tag_bonus is additive-only, never gating -- formality_fit
    alone still produces a valid, lower-scored candidate."""
    wardrobe = [
        _item("saree1", category="ethnic_saree", color="#8B0000", occasion_tags=["festival"]),
        _item("shoe1", category="footwear_formal", color="#000000", occasion_tags=["festival"]),
    ]
    occasion = _occasion(key="office", kind="professional", formality=6)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    assert len(result.candidates) >= 1
    assert result.candidates[0].total_score > 0.0
