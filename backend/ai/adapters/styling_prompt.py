"""Single prompt template shared by ``GeminiStylingAdapter`` and
``ClaudeStylingAdapter`` (SS-028 design §3.1, §8.3).

**Ownership note (``BL-101``):** SS-027's ticket makes "one rules module,
consumed by both the scorer and the prompt template" non-negotiable, but
SS-027 does not exist on this branch (separate worktree, no file overlap by
construction). This module is therefore a temporary single copy of the
colour/formality/occasion phrasing -- at SS-020 assembly, this module's rule
CONTENT must be replaced by SS-027's module, not duplicated alongside it.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from ai.ports.interfaces import StylePreferencesInput


class StylingPromptBuilder(Protocol):
    """Callable type alias adapters accept for injection (constructor arg
    ``prompt_builder``), matching ``build_styling_prompt``'s own signature
    exactly -- so a test double or a future SS-027 replacement can be
    swapped in without touching either adapter's constructor shape."""

    def __call__(
        self, preferences: StylePreferencesInput, *, max_suggestions: int
    ) -> str: ...


_INSTRUCTIONS = """You are a fashion-styling AI for an India-first wardrobe app.
Return ONLY structured JSON (no markdown, no prose) via the tool/schema you
were given -- a list of up to {max_suggestions} outfit suggestions, each
with item_category, label, an optional occasion, and a rationale.

Field guidance (mirrors this backend's own onboarding mapping doc):
- budget_range and gender are HARD FILTERS -- never suggest an item outside
  the stated budget band or ineligible for the stated gender.
- styles, wardrobe_type, occasions_priority, and favourite_colours are SOFT
  SIGNALS -- bias which suggestions you lead with, never used to justify
  omitting an otherwise-good, broadly-appropriate suggestion.
- Ethnic wear (kurta, saree, lehenga, anarkali, salwar kameez, sherwani,
  indo_western) is FIRST-CLASS, not a fallback category -- suggest it
  whenever it fits the occasion/style signals, exactly as often as western
  wear would be suggested in the same context.
- Never suggest white as a primary garment colour for a wedding_guest
  occasion (India-specific convention: white is associated with mourning).
- If the preferences below are empty or near-empty, return generic, broadly
  popular suggestions rather than refusing -- do not ask a clarifying
  question, this is a one-shot structured call with no follow-up turn.

User style preferences (JSON, any field may be absent or null):
{preferences_json}
"""


def build_styling_prompt(
    preferences: StylePreferencesInput, *, max_suggestions: int
) -> str:
    return _INSTRUCTIONS.format(
        max_suggestions=max_suggestions,
        preferences_json=preferences.model_dump_json(exclude_none=True),
    )


# ---------------------------------------------------------------------------
# SS-020 -- narration prompt (rank/narrate ALREADY-ASSEMBLED Engine v2
# candidates, never invent new ones).
# ---------------------------------------------------------------------------

class NarrationPromptBuilder(Protocol):
    """Callable type alias for ``build_narration_prompt``'s signature --
    same injection seam ``StylingPromptBuilder`` gives ``suggest_outfits``."""

    def __call__(
        self,
        candidates: list[dict[str, Any]],
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> str: ...


_NARRATION_INSTRUCTIONS = """You are a fashion-styling AI for an India-first wardrobe app.
Below is a list of ALREADY-ASSEMBLED outfit candidates for the occasion
"{occasion}" -- each was independently selected and scored by this app's own
deterministic engine. Your ONLY job is to write a short, friendly rationale
(English or Hindi) for up to {max_suggestions} of them, and optionally
re-rank them. You MUST echo back each candidate's "outfit_fingerprint"
field EXACTLY as given -- you must NEVER invent a new item, category, or
fingerprint not present in the candidates below. Return ONLY structured
JSON (no markdown, no prose) via the tool/schema you were given.

Field guidance (mirrors this backend's own onboarding mapping doc):
- Ethnic wear is FIRST-CLASS, not a fallback category.
- Never praise white as a primary garment colour for a wedding_guest
  occasion (India-specific convention: white is associated with mourning).
- Keep each rationale generic enough to be true regardless of exact colour
  shade -- do not claim a specific named colour beyond what the candidate's
  own category/explanation text already states.

User style preferences (JSON, any field may be absent or null):
{preferences_json}

Candidates (JSON array, each with items/score/explanation/gap_flags/outfit_fingerprint):
{candidates_json}
"""


def build_narration_prompt(
    candidates: list[dict[str, Any]],
    occasion: str,
    preferences: StylePreferencesInput,
    max_suggestions: int,
) -> str:
    """Sibling to ``build_styling_prompt`` -- renders ``render_candidate_for_prompt``'s
    dicts verbatim (never re-deriving colour/formality text itself, per that
    function's own stated contract)."""
    return _NARRATION_INSTRUCTIONS.format(
        occasion=occasion,
        max_suggestions=max_suggestions,
        preferences_json=preferences.model_dump_json(exclude_none=True),
        candidates_json=json.dumps(candidates),
    )
