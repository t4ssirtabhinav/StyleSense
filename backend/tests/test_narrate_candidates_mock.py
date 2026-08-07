"""Tests for MockStylingAdapter.narrate_candidates (SS-020)."""

from __future__ import annotations

from ai.adapters.mock_styling_adapter import MockStylingAdapter
from ai.ports.interfaces import StylePreferencesInput


def _candidate(fingerprint: str, explanation: str) -> dict[str, object]:
    return {
        "items": [{"id": "a", "category": "western_top"}],
        "score": 0.8,
        "explanation": explanation,
        "gap_flags": [],
        "outfit_fingerprint": fingerprint,
    }


async def test_never_invents_an_item_id_or_fingerprint_outside_input_candidates() -> None:
    adapter = MockStylingAdapter()
    candidates = [_candidate("fp1", "matches well"), _candidate("fp2", "also good")]
    result = await adapter.narrate_candidates(
        candidates, occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    input_fingerprints = {c["outfit_fingerprint"] for c in candidates}
    for narration in result.narrations:
        assert narration.outfit_fingerprint in input_fingerprints


async def test_rationale_is_built_purely_from_explanation_no_randomness() -> None:
    adapter = MockStylingAdapter()
    candidates = [_candidate("fp1", "matches your ethnic style; good colour harmony")]
    result1 = await adapter.narrate_candidates(
        candidates, occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    result2 = await adapter.narrate_candidates(
        candidates, occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result1.narrations[0].rationale == result2.narrations[0].rationale
    assert result1.narrations[0].rationale == "matches your ethnic style; good colour harmony"


async def test_max_suggestions_caps_the_result() -> None:
    adapter = MockStylingAdapter()
    candidates = [_candidate(f"fp{i}", f"reason {i}") for i in range(5)]
    result = await adapter.narrate_candidates(
        candidates, occasion="office", preferences=StylePreferencesInput(), max_suggestions=2
    )
    assert len(result.narrations) == 2


async def test_source_is_rules_only_never_raises() -> None:
    adapter = MockStylingAdapter()
    result = await adapter.narrate_candidates(
        [], occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result.source == "rules_only"
    assert result.narrations == []
