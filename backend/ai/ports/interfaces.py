"""Hexagonal port for outfit-styling AI providers (SS-006).

Onboarding field -> suggestion-engine effect mapping (this ticket's required
written mapping doc). Read this before writing a new adapter -- it is the
contract every ``IStylingProvider`` implementation must honor.

| Field                        | Effect                                                                                                          | Tier         |
|-------------------------------|------------------------------------------------------------------------------------------------------------------|--------------|
| ``styles[]``                  | Biases which style tags (e.g. "ethnic", "streetwear") rank higher; does not exclude non-matching styles.         | Soft signal  |
| ``wardrobe_type``             | Skews the western/ethnic mix of returned suggestions (e.g. ``mostly_ethnic`` -> ethnic-first ordering); doesn't  | Soft signal  |
|                                | exclude the other category.                                                                                      |              |
| ``occasions_priority[]``      | Biases which occasion categories are ranked first in Discover/Home feed, in list order; non-priority occasions   | Soft signal  |
| (max 3)                       | can still appear, just lower-ranked.                                                                              |              |
| ``budget_range``              | Excludes suggestions outside the selected price band entirely.                                                   | Hard filter  |
| ``favourite_colours[]``       | Biases colour-coordination scoring upward for matching/near hexes; doesn't exclude other colours.                | Soft signal  |
| (max 5, hex)                  |                                                                                                                    |              |
| ``gender``                    | Excludes catalog categories not eligible for the selected gender.                                                 | Hard filter  |

``budget_range`` and ``gender`` are HARD FILTERS: any conforming
``IStylingProvider`` implementation must actually exclude non-matching
suggestions for these two fields, not just weight them. Every other field is
a SOFT SIGNAL: it may re-rank or bias scoring, but must never exclude an
otherwise-eligible suggestion outright.

Mirrors ``mobile/features/onboarding/onboarding.types.ts``'s ``StylePreferences``
verbatim (see ``StylePreferencesInput`` below). ``styles``/``occasions_priority``
are ``list[str]`` (not a closed enum) because SS-004's 2026-07-13 revision
widened them to DB-backed taxonomy tables (``style_keywords``/``occasion_types``)
-- do not reintroduce a fixed Python ``Literal``/enum for either field.

Never modify ``IStylingProvider``'s signature to fit a new provider -- add a
new adapter class instead (Open/Closed, per CLAUDE.md).
"""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

GenderKey = Literal["woman", "man", "non_binary", "prefer_not_to_say"]
WardrobeTypeKey = Literal[
    "mostly_western", "mostly_ethnic", "equal_mix", "mostly_formal", "mostly_casual"
]
BudgetRangeKey = Literal["500_1000", "1000_3000", "3000_10000", "10000_plus"]


class StylePreferencesInput(BaseModel):
    """Mirrors mobile/features/onboarding/onboarding.types.ts's StylePreferences
    verbatim. All fields Optional[...] = None: style_preferences is a nullable
    JSONB column (types/supabase.ts) and onboarding is fully skippable per-step.
    styles/occasions_priority are list[str] (not a closed enum) because SS-004's
    2026-07-13 revision widened them to DB-backed taxonomies -- do not
    reintroduce a fixed Python Literal/enum here.
    """

    styles: list[str] | None = None
    wardrobe_type: WardrobeTypeKey | None = None
    occasions_priority: list[str] | None = None  # max 3, enforced client-side
    budget_range: BudgetRangeKey | None = None
    favourite_colours: list[str] | None = None  # hex codes, max 5
    gender: GenderKey | None = None


class OutfitSuggestionItem(BaseModel):
    item_category: str
    label: str
    occasion: str | None = None
    rationale: str


class OutfitSuggestionResult(BaseModel):
    user_id: str
    suggestions: list[OutfitSuggestionItem]
    generated_at: str  # ISO8601 UTC
    is_personalized: bool  # False on the null/empty-preferences degrade path
    source: Literal["mock", "gemini", "claude"] = "mock"


class IStylingProvider(ABC):
    """Never modify this signature to fit a new provider -- add a new adapter
    class instead (Open/Closed, per CLAUDE.md)."""

    @abstractmethod
    async def suggest_outfits(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> OutfitSuggestionResult:
        """Must degrade gracefully (generic suggestions, is_personalized=False)
        when preferences is effectively empty, rather than raise."""
        raise NotImplementedError
