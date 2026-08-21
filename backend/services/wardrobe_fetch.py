"""SS-048 -- ``fetch_wardrobe_for_styling``, extracted VERBATIM from
``OutfitPortfolioService._fetch_wardrobe`` (SS-020) so both the live
``POST /outfit-suggestions/portfolio`` endpoint and the new rail precompute
job (``services/rail_precompute_service.py``) build the engine's
``WardrobeItemInput`` map the SAME way -- one implementation, not two.

Pure extract-method refactor: behavior is byte-identical to the pre-SS-048
private method. ``OutfitPortfolioService._fetch_wardrobe`` becomes a
one-line delegation to this function (see that module) -- the existing
SS-020/22/23 test suite for that file is the regression guard proving this.
"""

from __future__ import annotations

import logging

from adapters.interfaces import IWardrobeRepository
from services.styling_rules_types import WardrobeItemInput

logger = logging.getLogger(__name__)


async def fetch_wardrobe_for_styling(
    *, jwt: str, user_id: str, wardrobe_repo: IWardrobeRepository
) -> dict[str, WardrobeItemInput]:
    rows = await wardrobe_repo.get_items_for_styling(jwt=jwt, user_id=user_id)
    items: dict[str, WardrobeItemInput] = {}
    for row in rows:
        try:
            item = WardrobeItemInput.model_validate(row)
        except Exception as exc:  # noqa: BLE001 -- one malformed row must never fail the whole request
            logger.warning(
                "wardrobe_fetch_row_skipped",
                extra={"user_id": user_id, "error": str(exc)},
            )
            continue
        items[item.id] = item
    return items
