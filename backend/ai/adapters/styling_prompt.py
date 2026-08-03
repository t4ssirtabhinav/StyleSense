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

from typing import Protocol

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
