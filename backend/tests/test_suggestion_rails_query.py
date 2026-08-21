"""Tests for backend/services/suggestion_rails_query.py (SS-048).

The "proof test" (test plan's central AC claim) asserts, two independent
ways, that this module never touches Engine v2: (1) an AST/source scan of
the module's own import statements, and (2) patching
``services.engine_v2.EngineV2.generate_portfolio`` to raise, then calling
both functions and asserting the mock was never invoked and no exception
propagated.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any
from unittest.mock import AsyncMock, patch

from services import suggestion_rails_query
from services.suggestion_rails_query import build_never_tried_pairs, build_not_yet_worn


class _FakeGarmentAttrs:
    def __init__(self, assembly_slot: str) -> None:
        self.assembly_slot = assembly_slot


_GARMENT_MAP = {
    "ethnic_kurta": _FakeGarmentAttrs("top"),
    "western_top": _FakeGarmentAttrs("top"),
    "ethnic_bottom": _FakeGarmentAttrs("bottom"),
    "jeans": _FakeGarmentAttrs("bottom"),
    "sneakers": _FakeGarmentAttrs("footwear"),
}


def _garment_lookup(category: str) -> Any:
    return _GARMENT_MAP.get(category)


def _row(
    item_id: str,
    category: str,
    *,
    wear_count: int = 0,
    do_not_style: bool = False,
    is_archived: bool = False,
    created_at: str = "2026-08-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "wear_count": wear_count,
        "do_not_style": do_not_style,
        "is_archived": is_archived,
        "created_at": created_at,
        "color_primary": "#000000",
    }


# ---------------------------------------------------------------------------
# build_never_tried_pairs
# ---------------------------------------------------------------------------


def test_build_never_tried_pairs_excludes_pairs_already_in_outfits_item_ids() -> None:
    items = [
        _row("top-1", "ethnic_kurta"),
        _row("bottom-1", "ethnic_bottom"),
        _row("bottom-2", "jeans"),
    ]
    previously_paired = [["top-1", "bottom-1"]]

    pairs = build_never_tried_pairs(
        items, garment_lookup=_garment_lookup, previously_paired_item_ids=previously_paired
    )

    assert ("top-1", "bottom-1") not in pairs
    assert ("top-1", "bottom-2") in pairs


def test_build_never_tried_pairs_excludes_do_not_style_and_is_archived_items() -> None:
    items = [
        _row("top-1", "ethnic_kurta", do_not_style=True),
        _row("top-2", "western_top", is_archived=True),
        _row("top-3", "ethnic_kurta"),
        _row("bottom-1", "jeans"),
    ]

    pairs = build_never_tried_pairs(
        items, garment_lookup=_garment_lookup, previously_paired_item_ids=[]
    )

    paired_top_ids = {top_id for top_id, _ in pairs}
    assert "top-1" not in paired_top_ids
    assert "top-2" not in paired_top_ids
    assert "top-3" in paired_top_ids


def test_build_never_tried_pairs_returns_empty_list_when_no_bottom_slot_items() -> None:
    items = [
        _row("top-1", "ethnic_kurta"),
        _row("shoe-1", "sneakers"),
    ]

    pairs = build_never_tried_pairs(
        items, garment_lookup=_garment_lookup, previously_paired_item_ids=[]
    )

    assert pairs == []


def test_build_never_tried_pairs_capped_at_limit() -> None:
    items = [_row(f"top-{i}", "ethnic_kurta") for i in range(5)] + [
        _row(f"bottom-{i}", "jeans") for i in range(5)
    ]

    pairs = build_never_tried_pairs(
        items, garment_lookup=_garment_lookup, previously_paired_item_ids=[], limit=3
    )

    assert len(pairs) == 3


# ---------------------------------------------------------------------------
# build_not_yet_worn
# ---------------------------------------------------------------------------


def test_build_not_yet_worn_returns_only_zero_wear_count_items() -> None:
    items = [
        _row("item-1", "ethnic_kurta", wear_count=0),
        _row("item-2", "jeans", wear_count=3),
        _row("item-3", "western_top", wear_count=0),
    ]

    result = build_not_yet_worn(items)

    assert set(result) == {"item-1", "item-3"}


def test_build_not_yet_worn_excludes_do_not_style_and_is_archived() -> None:
    items = [
        _row("item-1", "ethnic_kurta", wear_count=0, do_not_style=True),
        _row("item-2", "jeans", wear_count=0, is_archived=True),
        _row("item-3", "western_top", wear_count=0),
    ]

    result = build_not_yet_worn(items)

    assert result == ["item-3"]


def test_build_not_yet_worn_capped_at_limit() -> None:
    items = [_row(f"item-{i}", "ethnic_kurta", wear_count=0) for i in range(5)]

    result = build_not_yet_worn(items, limit=2)

    assert len(result) == 2


def test_build_not_yet_worn_returns_empty_list_for_fully_worn_wardrobe() -> None:
    items = [_row("item-1", "ethnic_kurta", wear_count=1)]

    result = build_not_yet_worn(items)

    assert result == []


# ---------------------------------------------------------------------------
# Proof test -- the ticket's central "zero marginal AI cost" claim.
# ---------------------------------------------------------------------------


def test_module_has_zero_engine_v2_imports_via_ast_scan() -> None:
    source = inspect.getsource(suggestion_rails_query)
    tree = ast.parse(source)
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append(node.module)

    assert not any("engine_v2" in name for name in imported_names), (
        f"suggestion_rails_query.py must import zero engine_v2* modules, found: {imported_names}"
    )


async def test_neither_function_ever_calls_engine_v2_generate_portfolio() -> None:
    items = [
        _row("top-1", "ethnic_kurta"),
        _row("bottom-1", "jeans"),
    ]

    with patch(
        "services.engine_v2.EngineV2.generate_portfolio",
        new=AsyncMock(side_effect=AssertionError("must never be called")),
    ) as mock_generate:
        pairs = build_never_tried_pairs(
            items, garment_lookup=_garment_lookup, previously_paired_item_ids=[]
        )
        not_yet_worn = build_not_yet_worn(items)

    assert pairs == [("top-1", "bottom-1")]
    assert not_yet_worn == ["top-1", "bottom-1"]
    mock_generate.assert_not_called()
