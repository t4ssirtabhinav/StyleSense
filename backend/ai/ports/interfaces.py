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
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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


@dataclass
class BackgroundRemovalResult:
    """Result of a single background-removal attempt (SS-011).

    A dataclass, not a Pydantic ``BaseModel`` like ``OutfitSuggestionResult``
    above -- ``image_bytes`` is a binary payload (a PNG with alpha channel),
    not a JSON-shaped value, so Pydantic's JSON-schema machinery buys nothing
    here and would force an awkward bytes<->base64 dance for no benefit.

    ``success=False`` (SDK raised, or the provider otherwise failed) never
    propagates the underlying exception to the caller -- the caller (
    ``WardrobeBgRemovalService``) is the one that owns retry/circuit-breaker
    policy, not this port.
    """

    success: bool
    image_bytes: bytes | None = None
    latency_ms: int | None = None
    error: str | None = None


class IBackgroundRemovalProvider(ABC):
    """Hexagonal port for image->image background-removal AI providers
    (SS-011). Distinct from ``IStylingProvider`` above (text/structured
    suggestions) and from SS-012's not-yet-created ``IVisionProvider``
    (image->structured-tags) -- a different capability from both.

    Never modify this signature to fit a new provider -- add a new adapter
    class instead (Open/Closed, per CLAUDE.md).
    """

    @abstractmethod
    async def remove_background(self, image_bytes: bytes) -> BackgroundRemovalResult:
        """Must never raise -- any SDK/network failure is caught and
        returned as ``BackgroundRemovalResult(success=False, error=...)`` so
        the caller can apply circuit-breaker/fallback policy uniformly."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SS-012 -- IVisionProvider (image -> structured India-taxonomy tags).
#
# This repo's first **vision** port -- distinct from IStylingProvider
# (text/structured outfit suggestions) and IBackgroundRemovalProvider
# (image -> image). Never modify this port's signature or GarmentTags'
# enum-backed fields to fit a new provider -- add a new adapter class
# instead (Open/Closed, per CLAUDE.md).
#
# Amendment 1 (2026-07-25): the original ticket/first Architect pass named
# `gemini-1.5-flash` + the `google-generativeai` SDK -- both were live-
# verified DEAD (not just unverified) during the amendment pass: the model
# was retired 2025-09-29 and the SDK's support ended 2025-11-30. This port
# and its adapter target the current model (`gemini-3.5-flash-lite`) and
# SDK (`google-genai`) instead -- see gemini_vision_adapter.py.
# ---------------------------------------------------------------------------

WardrobeCategory = Literal[
    # Transcribed verbatim from supabase/migrations/001_initial.sql (lines
    # 7-14), the real wardrobe_category DB enum -- 21 values, not the raw
    # ticket's "20-value" claim. The DB write rejects any non-member.
    "western_top",
    "western_bottom",
    "western_dress",
    "western_outerwear",
    "ethnic_kurta",
    "ethnic_saree",
    "ethnic_lehenga",
    "ethnic_anarkali",
    "ethnic_salwar_kameez",
    "ethnic_dupatta",
    "ethnic_sherwani",
    "indo_western",
    "footwear_formal",
    "footwear_casual",
    "footwear_ethnic",
    "footwear_sports",
    "accessory_bag",
    "accessory_jewellery",
    "accessory_watch",
    "accessory_belt",
    "accessory_scarf",
]

OccasionType = Literal[
    # Transcribed verbatim from supabase/migrations/001_initial.sql (lines
    # 18-21), the real occasion_type DB enum. occasion_tags is a real
    # occasion_type[] column -- validated strictly (an out-of-enum member
    # fails the whole payload), unlike SeasonTag/pattern/fabric below.
    "office",
    "casual",
    "date_night",
    "wedding_guest",
    "festival",
    "puja",
    "party",
    "travel",
    "workout",
    "beach",
    "formal_event",
    "college",
]

SeasonTag = Literal["summer", "winter", "monsoon", "all"]
"""``season_tags`` is a ``TEXT[]`` column, not a DB enum -- validated
against this closed set, but leniently (see GarmentTags' validator below):
an unknown value is dropped, not a whole-payload failure. India-first:
``monsoon`` is a first-class season, not folded into ``all``/``summer``."""

ContentFlag = Literal["ok", "nsfw", "not_clothing", "other"]
"""Resolves BL-044 (content moderation, deferred from SS-010). Distinct
from ``contains_person`` below -- a mirror selfie is a normal, non-NSFW way
to shoot an outfit, so "is a person visible" and "is this explicit/
not-clothing" are kept as two separate signals rather than conflated."""


class GarmentTags(BaseModel):
    """Structured output of a single Gemini vision-tagging pass (SS-012).

    ``category``/``occasion_tags`` are validated STRICTLY against the real
    DB enums (``wardrobe_category``, ``occasion_type``) -- an out-of-enum
    value on either fails the whole payload (a Pydantic ``ValidationError``
    the adapter catches and turns into ``VisionTaggingResult(success=False)``,
    never a raise). ``pattern``/``fabric``/``subcategory`` are free ``TEXT``
    columns in the DB, so kept as plain ``str | None`` with no enum
    enforcement -- an odd/out-of-vocabulary value must never nuke an
    otherwise-good result (risk-weighted: strict where the DB enforces an
    enum, lenient where it's free text). ``season_tags`` (``TEXT[]``, not a
    DB enum) is validated against SeasonTag's closed set but leniently --
    an unknown member is silently dropped rather than failing validation.

    ``category = None`` is a valid state (non-clothing photo, prompt-
    instructed ``confidence = 0.0``) -- not an error.
    """

    category: WardrobeCategory | None
    subcategory: str | None = None
    color_primary: str | None = None  # hex, e.g. "#1E3A8A"
    color_secondary: str | None = None
    pattern: str | None = None
    fabric: str | None = None
    occasion_tags: list[OccasionType] = Field(default_factory=list)
    season_tags: list[SeasonTag] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    content_flag: ContentFlag
    contains_person: bool
    alternatives: list[WardrobeCategory] | None = None
    """Top-2 category candidates for the Indo-Western fusion ambiguity edge
    case (SS-013 renders a disambiguation picker). ``None``/empty when the
    model is confident in a single category."""

    @field_validator("season_tags", mode="before")
    @classmethod
    def _drop_unknown_season_tags(cls, value: Any) -> Any:
        """Lenient by design (season_tags is free TEXT[], not a DB enum) --
        an out-of-vocabulary season is dropped, never fails the payload."""
        if value is None:
            return []
        valid = {"summer", "winter", "monsoon", "all"}
        return [v for v in value if isinstance(v, str) and v in valid]


class VisionTaggingResult(BaseModel):
    """Pydantic ``BaseModel`` (JSON-shaped, like ``OutfitSuggestionResult``)
    -- unlike the binary ``BackgroundRemovalResult`` dataclass, this result
    carries a rich structured payload, so Pydantic's JSON-schema machinery
    is a real fit here, not overkill."""

    success: bool
    tags: GarmentTags | None = None
    latency_ms: int | None = None
    model: str = "gemini-3.5-flash-lite"
    source: Literal["gemini", "cache", "mock"] = "gemini"
    error: str | None = None


class IVisionProvider(ABC):
    """Never modify this signature to fit a new provider -- add a new
    adapter class instead (Open/Closed, per CLAUDE.md)."""

    @abstractmethod
    async def tag_garment(self, image_bytes: bytes) -> VisionTaggingResult:
        """Must never raise -- any SDK/network/safety-block/parse/timeout
        failure is caught and returned as
        ``VisionTaggingResult(success=False, error=...)`` so the caller
        (``WardrobeTaggingService``) applies fallback policy uniformly."""
        raise NotImplementedError
