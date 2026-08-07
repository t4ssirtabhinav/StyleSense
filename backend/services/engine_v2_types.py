"""Pure typed data contracts for SS-038's Engine v2 pipeline.

No I/O of any kind lives here -- mirrors ``styling_rules_types.py``'s role
for the four-stage pipeline (eligibility, candidate search, attribute
scoring, portfolio select) in ``engine_v2.py``/``engine_v2_*.py``.

Reuses ``ScoredCandidate``/``RuleScore``/``GapReport``/``StylingRulesOverride``/
``WardrobeItemInput``/``OccasionStylingInput`` from ``styling_rules_types.py``
unchanged -- those shapes are not superseded, only their producer is
(``generate_candidates``/``score_candidate`` moved into the stage modules
below; ``render_candidate_for_prompt`` needs zero changes because
``ScoredCandidate``'s shape never changed).

``FabricAttributes`` physically lives in ``adapters/interfaces.py`` (so
``IFabricRegistryRepository`` can reference it without ``adapters/``
importing from ``services/``, this repo's established one-way import
direction) -- re-exported here so every pure stage module can import it from
this file like every other Engine v2 type, without needing to know that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from adapters.interfaces import FabricAttributes, WearRecency
from services.styling_rules_types import GapReport, ScoredCandidate, WardrobeItemInput

__all__ = [
    "GarmentSlot",
    "GarmentAttributes",
    "FabricAttributes",
    "WearRecency",
    "AssembledCandidate",
    "CandidateSearchResult",
    "EligibilityResult",
    "NoveltyInputs",
    "PortfolioCandidate",
    "EngineV2Result",
]

# Transcribed verbatim from supabase/migrations/014_garment_types_registry.sql's
# `slot` CHECK (12 values) -- do not re-derive from the epics doc or guess.
GarmentSlot = Literal[
    "head",
    "torso_base",
    "torso_mid",
    "legs",
    "full_body",
    "feet",
    "neck",
    "waist",
    "wrist",
    "carry",
    "drape",
    "set",
]


class GarmentAttributes(BaseModel):
    """One resolved ``garment_types`` row's Engine v2-relevant attributes,
    as returned by ``GarmentRegistryAdapter.get_garment_attributes``.
    ``assembly_slot`` is the engine's existing 6-value vocabulary
    (top/bottom/one_piece/outerwear/footwear/accessory), derived from
    ``garment_slot`` via ``styling_rules_defaults.GARMENT_SLOT_TO_ASSEMBLY_SLOT``.
    ``volume_class`` is pulled out of ``garment_types.styling_rules`` (open
    vocabulary, may be absent -- ``None`` means "no opinion", not a
    fabricated default)."""

    key: str
    assembly_slot: str
    garment_slot: GarmentSlot
    layer: int
    register: tuple[str, ...]
    base_formality: int
    pairs_with: tuple[str, ...]
    requires_with: tuple[str, ...]
    excludes_with: tuple[str, ...]
    volume_class: str | None = None


@dataclass(frozen=True)
class AssembledCandidate:
    """Stage②'s output, pre-scoring: one assembled combination of items
    plus any gap flags recorded during assembly (e.g. ``missing_footwear``)."""

    items: list[WardrobeItemInput]
    gap_flags: list[str]


@dataclass(frozen=True)
class CandidateSearchResult:
    """Stage②'s full result. ``total_base_pairs_considered`` is diagnostic
    and uncapped -- the property test's proof target that candidate count
    scales with wardrobe size rather than staying flat at the old ~72 cap."""

    candidates: list[AssembledCandidate]
    total_base_pairs_considered: int
    missing_slots: list[str]


@dataclass(frozen=True)
class EligibilityResult:
    """Stage①'s output: the wardrobe after dedupe, missing-field exclusion,
    and hard-colour-family exclusion (including the near-white guard)."""

    eligible_items: list[WardrobeItemInput]
    excluded_missing_color_or_category: int


@dataclass(frozen=True)
class NoveltyInputs:
    """Stage③'s novelty sub-term inputs, fetched once per
    ``generate_portfolio`` call by ``engine_v2_novelty.fetch_novelty_inputs``.

    ``recent_impression_item_counts`` is deliberately NOT occasion-filtered
    (``recent_impressions()`` isn't occasion-scoped by its own port) -- an
    item shown often anywhere is less novel to show again anywhere, a
    different axis from ``wear_recency_by_item``'s occasion-scoped fields."""

    wear_recency_by_item: dict[str, WearRecency] = field(default_factory=dict)
    recent_impression_item_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioCandidate:
    """One portfolio slot: a scored candidate plus whether it was selected
    as one of the 0-2 explicitly-labelled exploration picks."""

    candidate: ScoredCandidate
    is_exploration: bool
    strategy: str | None = None


@dataclass(frozen=True)
class EngineV2Result:
    """``EngineV2.generate_portfolio``'s return value."""

    portfolio: list[PortfolioCandidate]
    limited_options: bool
    gap_report: GapReport
    session_id: str | None
    engine_version: str = "engine-v2"
