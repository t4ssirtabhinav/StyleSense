"""Tests for backend/services/styling_rules_engine.py (SS-027).

**SS-038 (Engine v2) removed `generate_candidates`/`score_candidate` and
every private helper this file used to test directly** -- moved, not
duplicated, into `engine_v2_eligibility.py` (stage①), `engine_v2_candidate_search.py`
(stage②), `engine_v2_attribute_scoring.py` (stage③), and `engine_v2_colour.py`
(shared colour primitives). Their old test coverage now lives in
`test_engine_v2_eligibility.py`, `test_engine_v2_candidate_search.py`,
`test_engine_v2_attribute_scoring.py`, `test_engine_v2_colour.py`,
`test_engine_v2_portfolio.py`, `test_engine_v2_properties.py`, and
`test_engine_v2_integration.py` -- each removal below is a relocation, not a
regression, per SS-037's own precedent for touching shipped test
assertions.

Every test previously in this file that called `generate_candidates`/
`score_candidate`/`_resolve_styling_rules`/`_item_is_hard_excluded_white`
was REMOVED (those functions no longer exist in this module) -- see the
new-home test files listed above for equivalent coverage. The two
`render_candidate_for_prompt` tests below are KEPT, rewritten to build
their `ScoredCandidate` fixtures directly (that function's own shape is
unchanged, so its behaviour under test is identical; only the fixture-
construction mechanism changed, since it can no longer go through the
deleted `generate_candidates`).
"""

from __future__ import annotations

import json
from uuid import uuid4

from services.styling_rules_engine import render_candidate_for_prompt
from services.styling_rules_types import RuleScore, ScoredCandidate


def _scored_candidate(
    item_ids_and_categories: list[tuple[str, str]], *, score: float = 0.82
) -> ScoredCandidate:
    return ScoredCandidate(
        item_ids=[item_id for item_id, _ in item_ids_and_categories],
        category_labels={item_id: category for item_id, category in item_ids_and_categories},
        total_score=score,
        rule_scores=[
            RuleScore(
                rule="formality_fit", score=0.9, explanation="Formality fit 0.90 (tolerance 2)"
            ),
            RuleScore(rule="colour_harmony", score=0.85, explanation="Colour harmony 0.85"),
            RuleScore(
                rule="category_completeness", score=0.8, explanation="Outfit completeness 0.80"
            ),
        ],
        gap_flags=[],
    )


def test_render_candidate_for_prompt_is_json_serializable_and_compact() -> None:
    candidate = _scored_candidate(
        [
            ("i1", "ethnic_kurta"),
            ("i2", "western_bottom"),
            ("i3", "footwear_ethnic"),
            ("i4", "western_outerwear"),
        ]
    )
    rendered = render_candidate_for_prompt(candidate)
    serialized = json.dumps(rendered)
    json.loads(serialized)  # must round-trip without error
    # Char-count proxy (not an actual tokenizer count) for the ticket's own
    # ~800-token-for-5-candidates [ESTIMATE] budget -- unchanged from
    # SS-037's own measured budget for a <=4-item candidate.
    assert len(serialized) < 600


def test_render_candidate_for_prompt_stays_within_budget_for_max_size_candidate() -> None:
    """SS-037's own worst-case budget test (a ceremony/festival/religious
    candidate can carry up to 6 items), rebuilt directly against a
    ``ScoredCandidate`` fixture rather than via the deleted
    ``generate_candidates`` -- ``render_candidate_for_prompt`` itself is
    unchanged, so the measured 700-char budget still applies."""
    candidate = _scored_candidate(
        [
            (str(uuid4()), "ethnic_kurta"),
            (str(uuid4()), "western_bottom"),
            (str(uuid4()), "footwear_ethnic"),
            (str(uuid4()), "western_outerwear"),
            (str(uuid4()), "ethnic_dupatta"),
            (str(uuid4()), "accessory_jewellery"),
        ]
    )
    rendered = render_candidate_for_prompt(candidate)
    serialized = json.dumps(rendered)
    json.loads(serialized)  # must round-trip without error
    assert len(serialized) < 700


def test_render_candidate_for_prompt_picks_top_two_explanations() -> None:
    candidate = _scored_candidate([("i1", "ethnic_kurta"), ("i2", "western_bottom")])
    rendered = render_candidate_for_prompt(candidate)
    assert "Colour harmony" in rendered["explanation"] or "Formality fit" in rendered["explanation"]
    assert rendered["gap_flags"] == []
    assert rendered["score"] == 0.82


def test_render_candidate_for_prompt_carries_gap_flags() -> None:
    candidate = ScoredCandidate(
        item_ids=["i1"],
        category_labels={"i1": "ethnic_saree"},
        total_score=0.5,
        rule_scores=[RuleScore(rule="formality_fit", score=0.5, explanation="x")],
        gap_flags=["missing_footwear"],
    )
    rendered = render_candidate_for_prompt(candidate)
    assert rendered["gap_flags"] == ["missing_footwear"]


def test_render_candidate_for_prompt_budget_with_footwear_mismatch_flag() -> None:
    """BL-130's own re-verification trigger firing: SS-024's new
    ``footwear_formality_mismatch`` gap flag (§4.1) is rendered into the
    narration payload alongside the same worst-case 6-item ceremony
    candidate ``test_render_candidate_for_prompt_stays_within_budget_for_max_size_candidate``
    uses -- must still stay within the measured 700-char budget.

    Measured 2026-08-14 (SS-024 Developer phase): serialized length is
    **619 chars** against the 700-char budget -- a real datum (uuid4's
    36-char string form makes this deterministic across runs), not the
    design doc's ~626 arithmetic estimate, recorded here per BL-130's own
    requirement."""
    item_ids = [str(uuid4()) for _ in range(6)]
    categories = [
        "ethnic_kurta",
        "western_bottom",
        "footwear_sports",
        "western_outerwear",
        "ethnic_dupatta",
        "accessory_jewellery",
    ]
    candidate = ScoredCandidate(
        item_ids=item_ids,
        category_labels=dict(zip(item_ids, categories, strict=True)),
        total_score=0.82,
        rule_scores=[
            RuleScore(
                rule="formality_fit", score=0.9, explanation="Formality fit 0.90 (tolerance 2)"
            ),
            RuleScore(rule="colour_harmony", score=0.85, explanation="Colour harmony 0.85"),
            RuleScore(
                rule="category_completeness", score=0.7, explanation="Outfit completeness 0.70"
            ),
        ],
        gap_flags=["footwear_formality_mismatch"],
    )
    rendered = render_candidate_for_prompt(candidate)
    serialized = json.dumps(rendered)
    json.loads(serialized)  # must round-trip without error
    assert len(serialized) == 619
    assert len(serialized) < 700
