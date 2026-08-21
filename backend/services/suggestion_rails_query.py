"""SS-048 -- pure query-layer logic for the ``never_tried_pairs``/
``not_yet_worn`` rails.

**ZERO imports from ``services.engine_v2*`` -- this is the ticket's central
"zero marginal AI cost" claim, and it is enforced structurally, not just by
convention.** Both functions here operate ONLY on already-fetched data
(wardrobe rows from ``IWardrobeRepository.get_items_for_rails``, a
``garment_lookup`` callable duck-typed against whatever
``GarmentRegistryAdapter.get_garment_attributes`` returns -- never imported
by *type* either, to keep this module's import list genuinely empty of
anything named ``engine_v2*``, and ``outfits.item_ids`` rows from
``IOutfitRepository.get_item_ids_for_user``). No Engine v2 stage, no
``EngineV2`` call, no scoring of any kind.

This is this codebase's own established convention for "deterministic,
engine-adjacent logic" (mirrors ``engine_v2_eligibility.filter_eligible``/
``engine_v2_novelty.fetch_novelty_inputs``'s own "pure stage function over
already-fetched data" shape) -- deliberately NOT hand-written ``NOT EXISTS``
SQL (the competitive doc's own framing), which also sidesteps a real gap:
``wardrobe_category``'s enum has no dedicated "ethnic bottom" value, so a
category-name-based SQL ``top x bottom`` join can't be written correctly
today anyway. ``garment_lookup`` (an assembly-slot resolver, e.g.
``GarmentRegistryAdapter.get_garment_attributes``) is how this module still
gets a correct top/bottom bucketing without that gap -- ``rail_precompute_
service.py`` (which DOES import ``engine_v2*`` freely) is the one that awaits
``garment_registry_adapter.refresh()`` and passes the bound method in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

__all__ = ["build_never_tried_pairs", "build_not_yet_worn"]

_DEFAULT_NEVER_TRIED_PAIRS_LIMIT = 10
_DEFAULT_NOT_YET_WORN_LIMIT = 10


def _is_lifecycle_eligible(row: dict[str, Any]) -> bool:
    return not row.get("do_not_style") and not row.get("is_archived")


def _assembly_slot(category: str | None, garment_lookup: Callable[[str], Any]) -> str | None:
    """Duck-typed against whatever ``garment_lookup`` returns (an object
    with an ``.assembly_slot`` attribute, e.g.
    ``services.engine_v2_types.GarmentAttributes`` -- never imported here by
    name, see module docstring). ``None`` for a missing/unresolvable
    category, never an exception."""
    if not category:
        return None
    attrs = garment_lookup(category)
    if attrs is None:
        return None
    return getattr(attrs, "assembly_slot", None)


def _sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("created_at") or ""), str(row.get("id")))


def build_never_tried_pairs(
    items: Sequence[dict[str, Any]],
    *,
    garment_lookup: Callable[[str], Any],
    previously_paired_item_ids: Sequence[Sequence[str]],
    limit: int = _DEFAULT_NEVER_TRIED_PAIRS_LIMIT,
) -> list[tuple[str, str]]:
    """Cartesian ``top x bottom`` over the caller's own wardrobe rows, minus
    any pair where both ids already appear together in the same
    ``outfits.item_ids`` row (pure Python set membership) -- excludes
    ``do_not_style``/``is_archived`` items even when otherwise a valid pair.
    Deterministic (sorted by ``(created_at, id)``), capped at ``limit``.
    Returns ``[]``, never raises, when the wardrobe has no bottom-slot (or
    no top-slot) items at all -- the cartesian product is empty by
    construction."""
    eligible = [row for row in items if _is_lifecycle_eligible(row)]
    tops = sorted(
        (row for row in eligible if _assembly_slot(row.get("category"), garment_lookup) == "top"),
        key=_sort_key,
    )
    bottoms = sorted(
        (
            row
            for row in eligible
            if _assembly_slot(row.get("category"), garment_lookup) == "bottom"
        ),
        key=_sort_key,
    )

    already_paired: list[frozenset[str]] = [
        frozenset(str(item_id) for item_id in row) for row in previously_paired_item_ids if row
    ]

    pairs: list[tuple[str, str]] = []
    for top in tops:
        top_id = str(top["id"])
        for bottom in bottoms:
            bottom_id = str(bottom["id"])
            pair = frozenset({top_id, bottom_id})
            if any(pair <= paired for paired in already_paired):
                continue
            pairs.append((top_id, bottom_id))
            if len(pairs) >= limit:
                return pairs
    return pairs


def build_not_yet_worn(
    items: Sequence[dict[str, Any]],
    *,
    limit: int = _DEFAULT_NOT_YET_WORN_LIMIT,
) -> list[str]:
    """``wear_count == 0`` items, excluding ``do_not_style``/``is_archived``,
    newest-first (``created_at`` desc, then ``id`` for determinism), capped
    at ``limit``. Returns ``[]``, never raises, for a fully-worn wardrobe."""
    eligible = [
        row
        for row in items
        if _is_lifecycle_eligible(row) and int(row.get("wear_count") or 0) == 0
    ]
    ordered = sorted(eligible, key=_sort_key, reverse=True)
    return [str(row["id"]) for row in ordered[:limit]]
