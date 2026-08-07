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
widened them to DB-backed taxonomy tables (``style_keywords`` and, since
SS-025, the ``occasions`` registry that superseded ``occasion_types``)
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


class NarratedCandidate(BaseModel):
    """(SS-020) One LLM-narrated Engine v2 candidate. ``outfit_fingerprint``
    ties back to ``engine_v2_portfolio.compute_outfit_fingerprint`` -- this
    is the ONLY way a caller re-associates a narration with its own
    candidate, never trusting the LLM's own ordering."""

    outfit_fingerprint: str  # ties back to engine_v2_portfolio.compute_outfit_fingerprint
    rationale: str           # English or Hindi prose, per AC #2
    rank: int | None = None  # LLM's own re-ranking within the supplied set, if it re-ranks; None = kept input order


class NarratedPortfolioResult(BaseModel):
    """(SS-020) ``IStylingProvider.narrate_candidates``'s return shape."""

    narrations: list[NarratedCandidate]
    language: Literal["en", "hi"] = "en"
    source: Literal["mock", "gemini", "claude", "rules_only"] = "rules_only"


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

    @abstractmethod
    async def narrate_candidates(
        self,
        candidates: list[dict[str, Any]],  # engine_v2_types.render_candidate_for_prompt(...) output, one dict per candidate, UNCHANGED shape
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> NarratedPortfolioResult:
        """(SS-020, additive port capability -- same class of change SS-039
        made to ``IRateLimiter.peek()``) MUST NEVER invent an item id/
        category not present in ``candidates`` -- this is what makes
        SS-020's 'no hallucinated item IDs' AC structurally provable (same
        posture Engine v2 already gives ``ScoredCandidate.item_ids``). MUST
        NEVER raise -- any SDK/parse/timeout failure is caught and mapped
        to ``StylingCall``'s existing ``ProviderXxxError`` hierarchy exactly
        like ``suggest_outfits_with_metrics`` does, so ``StylingRouter``'s
        chain/failover/degrade logic (unmodified) works identically for
        this method."""
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

# (SS-025) The ``OccasionType`` Literal is GONE, along with the
# ``occasion_type`` DB enum it transcribed. ``wardrobe_items.occasion_tags``
# is now ``TEXT[]`` of slugs from the data-driven ``occasions`` registry --
# adding an occasion is an INSERT, so no closed Python Literal can enumerate
# them. Do NOT reintroduce one.
#
# Vocabulary checking moved to ``services/occasion_normalizer.py``, which has
# DB access; this module stays I/O-free. See ``GarmentTags`` below for the
# resulting strict-to-lenient posture change.

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

    ``category`` is validated STRICTLY against the real ``wardrobe_category``
    DB enum -- an out-of-enum value fails the whole payload (a Pydantic
    ``ValidationError`` the adapter catches and turns into
    ``VisionTaggingResult(success=False)``, never a raise).
    ``pattern``/``fabric``/``subcategory`` are free ``TEXT`` columns in the
    DB, so kept as plain ``str | None`` with no enum enforcement -- an
    odd/out-of-vocabulary value must never nuke an otherwise-good result
    (risk-weighted: strict where the DB enforces an enum, lenient where it's
    free text). ``season_tags`` (``TEXT[]``, not a DB enum) is validated
    against SeasonTag's closed set but leniently -- an unknown member is
    silently dropped rather than failing validation.

    (SS-025) ``occasion_tags`` moved from *strict, out-of-vocabulary fails
    the payload* to **lenient-with-capture**, matching ``pattern``/
    ``fabric``'s existing posture. The ``occasion_type`` enum is gone; the
    column is ``TEXT[]`` of registry slugs, and an occasion the registry
    hasn't modelled yet is a SIGNAL, not an error (the raw ticket's own
    edge case: "store it and log it for review rather than dropping the tag
    or failing the item write"). The validator below only coerces SHAPE --
    it deliberately performs NO vocabulary check, because that needs DB
    access; ``services/occasion_normalizer.py`` owns resolution, and the DB
    trigger + ``occasion_unknown_tags`` own capture.

    ``category = None`` is a valid state (non-clothing photo, prompt-
    instructed ``confidence = 0.0``) -- not an error.
    """

    category: WardrobeCategory | None
    subcategory: str | None = None
    color_primary: str | None = None  # hex, e.g. "#1E3A8A"
    color_secondary: str | None = None
    pattern: str | None = None
    fabric: str | None = None
    occasion_tags: list[str] = Field(default_factory=list)
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

    @field_validator("occasion_tags", mode="before")
    @classmethod
    def _coerce_occasion_tags(cls, value: Any) -> Any:
        """(SS-025) SHAPE coercion only -- deliberately no vocabulary check.

        Accepts ``None`` (-> ``[]``), a bare string (-> one-element list, a
        shape some models emit for a single tag), or a list. Non-string
        members and members that are blank after trimming are dropped;
        everything else is kept verbatim, including occasions the registry
        has never heard of. Resolution against ``occasions``/
        ``occasion_aliases`` is ``OccasionNormalizer``'s job (it has DB
        access; this module is I/O-free), and capture is the DB trigger's.

        The whole point is that an unmodelled occasion NEVER fails the
        payload -- the inverse of the pre-SS-025 behaviour.
        """
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]


class TokenUsage(BaseModel):
    """(SS-029) Per-call token usage, when the provider's SDK exposes it.
    Additive, optional field on ``VisionTaggingResult`` below -- does NOT
    change ``IVisionProvider.tag_garment``'s signature (Open/Closed, per
    CLAUDE.md). Feeds ``WardrobeTaggingService``'s post-call cost
    reconciliation (``PriceTable.cost(..., tokens_in=..., tokens_out=...)``);
    when a call has no ``usage``, the caller falls back to the price row's
    ``default_tokens_in/out`` with ``pricing_status='estimated'`` rather
    than a silent zero (design §7 Q1)."""

    tokens_in: int
    tokens_out: int


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
    usage: TokenUsage | None = None


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
