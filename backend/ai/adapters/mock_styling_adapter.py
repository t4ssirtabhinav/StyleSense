"""Rule-based stub implementation of ``IStylingProvider`` (SS-006).

Makes no external API calls. Exists to prove the ``ai/ports/interfaces.py``
mapping doc's hard-filter/soft-signal distinction is real behavior, not just
prose: ``budget_range`` and ``gender`` are applied as actual exclusion
filters against a small static catalog; every other field is applied as a
weighting/reordering pass over what's left.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai.adapters.styling_call import is_effectively_empty as _is_effectively_empty
from ai.ports.interfaces import (
    IStylingProvider,
    OutfitSuggestionItem,
    OutfitSuggestionResult,
    StylePreferencesInput,
)

# A small static catalog. Each entry is tagged with the attributes the
# mapping doc's hard filters / soft signals reason over. Not a real product
# catalog -- just enough shape to exercise the mapping logic.
_CATALOG: list[dict[str, object]] = [
    {
        "item_category": "ethnic_kurta",
        "label": "Cotton Anarkali Kurta",
        "occasion": "festival",
        "styles": ["ethnic", "traditional"],
        "wardrobe_type": "mostly_ethnic",
        "budget_tier": "1000_3000",
        "genders": ["woman", "non_binary", "prefer_not_to_say"],
        "colours": ["#B22222", "#FFD700"],
    },
    {
        "item_category": "western_top",
        "label": "Linen Button-Down Shirt",
        "occasion": "office",
        "styles": ["minimalist", "formal"],
        "wardrobe_type": "mostly_formal",
        "budget_tier": "500_1000",
        "genders": ["man", "non_binary", "prefer_not_to_say"],
        "colours": ["#FFFFFF", "#87CEEB"],
    },
    {
        "item_category": "western_dress",
        "label": "Wrap Midi Dress",
        "occasion": "date_night",
        "styles": ["chic", "streetwear"],
        "wardrobe_type": "mostly_western",
        "budget_tier": "1000_3000",
        "genders": ["woman", "non_binary", "prefer_not_to_say"],
        "colours": ["#000000", "#8B0000"],
    },
    {
        "item_category": "indo_western",
        "label": "Nehru Jacket Co-ord Set",
        "occasion": "wedding_guest",
        "styles": ["ethnic", "fusion"],
        "wardrobe_type": "equal_mix",
        "budget_tier": "3000_10000",
        "genders": ["man", "non_binary", "prefer_not_to_say"],
        "colours": ["#4B0082", "#DAA520"],
    },
    {
        "item_category": "footwear_casual",
        "label": "Canvas Sneakers",
        "occasion": "casual",
        "styles": ["streetwear", "minimalist"],
        "wardrobe_type": "mostly_casual",
        "budget_tier": "500_1000",
        "genders": ["woman", "man", "non_binary", "prefer_not_to_say"],
        "colours": ["#FFFFFF", "#000000"],
    },
    {
        "item_category": "ethnic_saree",
        "label": "Silk Blend Saree",
        "occasion": "puja",
        "styles": ["ethnic", "traditional"],
        "wardrobe_type": "mostly_ethnic",
        "budget_tier": "10000_plus",
        "genders": ["woman", "non_binary", "prefer_not_to_say"],
        "colours": ["#B22222", "#4B0082"],
    },
    {
        "item_category": "western_outerwear",
        "label": "Structured Blazer",
        "occasion": "office",
        "styles": ["formal", "chic"],
        "wardrobe_type": "mostly_formal",
        "budget_tier": "3000_10000",
        "genders": ["woman", "man", "non_binary", "prefer_not_to_say"],
        "colours": ["#000000", "#808080"],
    },
    {
        "item_category": "accessory_jewellery",
        "label": "Oxidised Silver Jhumkas",
        "occasion": "festival",
        "styles": ["ethnic"],
        "wardrobe_type": "mostly_ethnic",
        "budget_tier": "500_1000",
        "genders": ["woman", "non_binary", "prefer_not_to_say"],
        "colours": ["#C0C0C0"],
    },
]

_GENERIC_FALLBACK: list[OutfitSuggestionItem] = [
    OutfitSuggestionItem(
        item_category="western_top",
        label="Classic White Shirt",
        occasion="casual",
        rationale="A versatile popular pick shown while your style profile is empty.",
    ),
    OutfitSuggestionItem(
        item_category="ethnic_kurta",
        label="Everyday Cotton Kurta",
        occasion="casual",
        rationale="A versatile popular pick shown while your style profile is empty.",
    ),
    OutfitSuggestionItem(
        item_category="footwear_casual",
        label="Canvas Sneakers",
        occasion="casual",
        rationale="A versatile popular pick shown while your style profile is empty.",
    ),
]


def _hex_distance(a: str, b: str) -> int:
    """Cheap colour-closeness heuristic: sum of per-channel absolute diffs.

    Not perceptual colour science -- just enough to bias ranking toward
    near-matching hexes, per the mapping doc's "soft signal" for
    ``favourite_colours``.
    """
    a = a.lstrip("#")
    b = b.lstrip("#")
    if len(a) != 6 or len(b) != 6:
        return 255 * 3
    try:
        return sum(abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return 255 * 3


class MockStylingAdapter(IStylingProvider):
    """Canned, rule-based stub. No external API calls."""

    async def suggest_outfits(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> OutfitSuggestionResult:
        now_iso = datetime.now(UTC).isoformat()

        if _is_effectively_empty(preferences):
            return OutfitSuggestionResult(
                user_id="",
                suggestions=_GENERIC_FALLBACK[:max_suggestions],
                generated_at=now_iso,
                is_personalized=False,
                source="mock",
            )

        # --- Hard filters: budget_range, gender ---
        candidates = list(_CATALOG)

        if preferences.budget_range is not None:
            candidates = [c for c in candidates if c["budget_tier"] == preferences.budget_range]

        if preferences.gender is not None:
            candidates = [
                c for c in candidates if preferences.gender in c["genders"]  # type: ignore[operator]
            ]

        # --- Soft signals: styles, wardrobe_type, occasions_priority, favourite_colours ---
        def score(item: dict[str, object]) -> float:
            points = 0.0

            item_styles = item["styles"]
            if preferences.styles and isinstance(item_styles, list):
                if any(s in item_styles for s in preferences.styles):
                    points += 3.0

            if preferences.wardrobe_type is not None and item["wardrobe_type"] == preferences.wardrobe_type:
                points += 2.0

            if preferences.occasions_priority:
                item_occasion = item["occasion"]
                if item_occasion in preferences.occasions_priority:
                    # Earlier in the priority list -> higher weight.
                    rank = preferences.occasions_priority.index(str(item_occasion))
                    points += max(0.0, 3.0 - rank)

            item_colours = item["colours"]
            if preferences.favourite_colours and isinstance(item_colours, list):
                best = min(
                    (_hex_distance(fav, colour) for fav in preferences.favourite_colours for colour in item_colours),
                    default=255 * 3,
                )
                # Closer colours (smaller distance) contribute more points.
                points += max(0.0, (255 * 3 - best) / (255 * 3)) * 2.0

            return points

        ranked = sorted(candidates, key=score, reverse=True)

        suggestions = [
            OutfitSuggestionItem(
                item_category=str(item["item_category"]),
                label=str(item["label"]),
                occasion=str(item["occasion"]),
                rationale=_build_rationale(item, preferences),
            )
            for item in ranked[:max_suggestions]
        ]

        if not suggestions:
            # Hard filters excluded everything (e.g. an unusually narrow
            # budget/gender combination against this tiny mock catalog) --
            # degrade rather than return an empty list.
            return OutfitSuggestionResult(
                user_id="",
                suggestions=_GENERIC_FALLBACK[:max_suggestions],
                generated_at=now_iso,
                is_personalized=False,
                source="mock",
            )

        return OutfitSuggestionResult(
            user_id="",
            suggestions=suggestions,
            generated_at=now_iso,
            is_personalized=True,
            source="mock",
        )


def _build_rationale(item: dict[str, object], preferences: StylePreferencesInput) -> str:
    reasons = []
    item_styles = item["styles"]
    if preferences.styles and isinstance(item_styles, list):
        matched = [s for s in preferences.styles if s in item_styles]
        if matched:
            reasons.append(f"matches your {', '.join(matched)} style")
    if preferences.wardrobe_type is not None and item["wardrobe_type"] == preferences.wardrobe_type:
        reasons.append(f"fits your {preferences.wardrobe_type} wardrobe preference")
    if preferences.occasions_priority and item["occasion"] in preferences.occasions_priority:
        reasons.append(f"suited for {item['occasion']}, one of your priority occasions")
    if preferences.budget_range is not None:
        reasons.append(f"within your {preferences.budget_range} budget")
    if not reasons:
        reasons.append("a popular pick within your preferences")
    return "Suggested because it " + "; ".join(reasons) + "."
