"""Pure typed data contracts for SS-027's styling rules engine.

No I/O of any kind lives here -- these are Pydantic ``BaseModel``s (mirroring
``ai/ports/interfaces.py``'s ``OutfitSuggestionResult``/``GarmentTags``
convention, not dataclasses) because these shapes are meant to be
JSON-serialized into a future API response / LLM prompt.

``WardrobeCategory``/``SeasonTag`` are imported from ``ai/ports/interfaces.py``
(the schema-transcription source of truth for both) -- never redefined here.

``StylingRulesOverride`` is the documented schema for what a non-empty
``occasions.styling_rules`` JSONB value means (currently ``'{}'::jsonb`` for
all 12 seeded rows -- see ``styling_rules_defaults.py``). This is
INTENTIONALLY the only place this shape is defined: any future migration or
dashboard edit to ``occasions.styling_rules`` must write against this schema.
All fields are ``Optional[...] = None`` and validated LENIENTLY (unknown keys
ignored, wrong-typed values dropped to ``None`` rather than raising) --
mirrors ``GarmentTags``' established lenient-validator posture, since
``styling_rules`` is hand-editable via the Supabase Dashboard (service_role
bypasses RLS) and therefore untrusted-shaped.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from ai.ports.interfaces import SeasonTag, StylePreferencesInput, WardrobeCategory

__all__ = [
    "WardrobeItemInput",
    "OccasionStylingInput",
    "StylingRulesOverride",
    "RuleScore",
    "ScoredCandidate",
    "GapReport",
    "PreFilterResult",
    "StylePreferencesInput",
]

# Transcribed verbatim from supabase/migrations/007_occasions_registry.sql
# lines 42-44 (the live `kind` CHECK constraint) -- do not re-derive from the
# epics doc or guess.
OccasionKind = Literal[
    "everyday",
    "ceremony",
    "festival",
    "travel",
    "sport",
    "professional",
    "social",
    "milestone",
    "religious",
]

RequiredBase = Literal["top_bottom", "one_piece", "either"]


class WardrobeItemInput(BaseModel):
    """One wardrobe item, as fetched by whoever wires this module in later
    (out of this ticket's scope -- see design doc's Open Questions)."""

    id: str
    category: WardrobeCategory | None = None
    color_primary: str | None = None  # hex, e.g. "#1E3A8A"
    color_secondary: str | None = None
    pattern: str | None = None
    fabric: str | None = None
    occasion_tags: list[str] = Field(default_factory=list)
    season_tags: list[SeasonTag] = Field(default_factory=list)
    wear_count: int = 0
    last_worn_at: date | None = None


class OccasionStylingInput(BaseModel):
    """The occasion context a caller supplies. ``styling_rules`` is raw
    JSONB as fetched -- may be ``{}``, may be partial, may be hand-edited
    garbage; this module never trusts its shape (see ``StylingRulesOverride``
    below)."""

    key: str
    kind: OccasionKind
    formality: int = Field(ge=0, le=10)
    styling_rules: dict[str, Any] = Field(default_factory=dict)


class StylingRulesOverride(BaseModel):
    """The documented schema for a non-empty ``occasions.styling_rules``
    JSONB value. All fields optional and validated leniently: unknown keys
    are ignored (Pydantic's default `extra="ignore"` behaviour), and a
    wrong-typed value for a known field is dropped to ``None`` rather than
    raising -- mirrors ``GarmentTags``' lenient-validator posture, since this
    JSONB column is hand-editable and therefore untrusted-shaped.

    THIS IS THE ONLY PLACE THIS SHAPE IS DEFINED -- any future migration or
    dashboard edit to ``occasions.styling_rules`` must write against this
    schema.
    """

    required_base: RequiredBase | None = None
    footwear_required: bool | None = None
    outerwear_required: bool | None = None
    preferred_footwear_categories: list[str] | None = None
    preferred_accessory_categories: list[str] | None = None
    excluded_color_families: list[str] | None = None
    formality_tolerance: int | None = None

    @classmethod
    def parse_lenient(cls, raw: dict[str, Any] | None) -> StylingRulesOverride:
        """Field-by-field lenient parse: unknown keys ignored (never even
        looked at); a per-field wrong-typed value is dropped to ``None``
        (which then falls back to the kind default for that one field, see
        ``styling_rules_engine._resolve_styling_rules``) rather than failing
        the whole payload. Mirrors ``GarmentTags``' established
        lenient-validator posture -- this JSONB column is hand-editable via
        the Supabase Dashboard (``service_role`` bypasses RLS) and therefore
        untrusted-shaped. Never raises."""
        if not isinstance(raw, dict):
            return cls()
        kwargs: dict[str, Any] = {}
        for name, field_info in cls.model_fields.items():
            if name not in raw:
                continue
            value = raw[name]
            if value is None:
                kwargs[name] = None
                continue
            adapter: TypeAdapter[Any] = TypeAdapter(field_info.annotation)
            try:
                kwargs[name] = adapter.validate_python(value)
            except ValidationError:
                kwargs[name] = None
        return cls(**kwargs)


class RuleScore(BaseModel):
    """One scoring rule's contribution to a candidate's total score. The
    ``explanation`` string is short and human-readable -- this is the exact
    string a future prompt template embeds verbatim (the "consumed twice"
    contract), never re-derived by the prompt-builder."""

    rule: str
    score: float = Field(ge=0.0, le=1.0)
    explanation: str


class ScoredCandidate(BaseModel):
    """One assembled, scored outfit candidate. ``item_ids`` references only
    real input ``wardrobe_item.id`` values -- this is what makes SS-020's
    "item IDs must not be hallucinated" AC structurally impossible to fail."""

    item_ids: list[str]
    category_labels: dict[str, str]  # item id -> category label
    total_score: float = Field(ge=0.0, le=1.0)
    rule_scores: list[RuleScore]
    gap_flags: list[str] = Field(default_factory=list)


class GapReport(BaseModel):
    """Occasion-level aggregate gap info, distinct from a per-candidate
    ``gap_flags`` entry."""

    excluded_missing_color_or_category: int = 0
    missing_slots: list[str] = Field(default_factory=list)


class PreFilterResult(BaseModel):
    candidates: list[ScoredCandidate]
    limited_options: bool
    gap_report: GapReport
