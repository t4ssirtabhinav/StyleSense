"""Tests for backend/ai/adapters/mock_styling_adapter.py (SS-006).

Exercises the mapping doc's hard-filter (budget_range, gender) vs
soft-signal (everything else) distinction as real behavior, not just prose.
"""

from __future__ import annotations

import pytest

from ai.adapters.mock_styling_adapter import MockStylingAdapter
from ai.ports.interfaces import StylePreferencesInput


@pytest.fixture
def adapter() -> MockStylingAdapter:
    return MockStylingAdapter()


async def test_full_preferences_is_personalized(adapter: MockStylingAdapter) -> None:
    preferences = StylePreferencesInput(
        styles=["ethnic", "traditional"],
        wardrobe_type="mostly_ethnic",
        occasions_priority=["festival", "puja"],
        budget_range="1000_3000",
        favourite_colours=["#B22222"],
        gender="woman",
    )

    result = await adapter.suggest_outfits(preferences, max_suggestions=5)

    assert result.is_personalized is True
    assert len(result.suggestions) <= 5
    assert result.source == "mock"


async def test_all_none_preferences_degrades_without_raising(
    adapter: MockStylingAdapter,
) -> None:
    preferences = StylePreferencesInput()

    result = await adapter.suggest_outfits(preferences, max_suggestions=5)

    assert result.is_personalized is False
    assert len(result.suggestions) > 0


async def test_partial_preferences_only_styles_set(adapter: MockStylingAdapter) -> None:
    preferences = StylePreferencesInput(styles=["streetwear"])

    result = await adapter.suggest_outfits(preferences, max_suggestions=5)

    assert len(result.suggestions) > 0


async def test_different_budget_ranges_produce_disjoint_suggestions(
    adapter: MockStylingAdapter,
) -> None:
    cheap = await adapter.suggest_outfits(
        StylePreferencesInput(budget_range="500_1000"), max_suggestions=10
    )
    expensive = await adapter.suggest_outfits(
        StylePreferencesInput(budget_range="10000_plus"), max_suggestions=10
    )

    cheap_labels = {item.label for item in cheap.suggestions}
    expensive_labels = {item.label for item in expensive.suggestions}

    assert cheap_labels, "expected at least one suggestion for the cheap budget band"
    assert expensive_labels, "expected at least one suggestion for the expensive budget band"
    assert cheap_labels.isdisjoint(expensive_labels)


async def test_gender_excludes_ineligible_categories(adapter: MockStylingAdapter) -> None:
    result = await adapter.suggest_outfits(
        StylePreferencesInput(gender="man"), max_suggestions=10
    )

    # These catalog categories are marked eligible only for
    # woman/non_binary/prefer_not_to_say in the mock catalog.
    woman_only_categories = {"ethnic_saree", "ethnic_kurta", "western_dress", "accessory_jewellery"}
    returned_categories = {item.item_category for item in result.suggestions}

    assert returned_categories.isdisjoint(woman_only_categories)
