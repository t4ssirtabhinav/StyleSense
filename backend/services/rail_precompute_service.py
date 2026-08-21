"""SS-048 -- ``RailPrecomputeService.recompute_all_rails``: the one job that
writes all four ``suggestion_rails`` rows for a user.

``todays_picks``/``newest_pieces`` share a SINGLE ``EngineV2.generate_portfolio``
call (widened ``portfolio_size_range=(15, 20)``), sliced two ways --
satisfies the AC's "no second scoring implementation" literally. Uses the
SAME occasion-resolution/wardrobe-fetch logic the live
``POST /outfit-suggestions/portfolio`` endpoint uses
(``services.occasion_resolution``/``services.wardrobe_fetch``, extracted
from ``OutfitPortfolioService`` for exactly this reuse -- SS-048's riskiest
refactor).

``never_tried_pairs``/``not_yet_worn`` are the pure query-layer functions in
``services.suggestion_rails_query`` -- zero engine involvement.

Every payload item (all four rails) carries a compute-time DISPLAY SNAPSHOT
(``{item_id, category, color_primary, thumbnail_url}``), mirroring
``outfits.items_snapshot``'s own denormalisation rationale (``020_outfits_
first_writer.sql``): a since-deleted item must not corrupt or crash a later
read of a cached rail (``GET /suggestion-rails`` never re-joins
``wardrobe_items``). ``outfit_fingerprint`` on the two engine-backed rails'
payload items uses ``engine_v2_portfolio.compute_outfit_fingerprint``
EXCLUSIVELY (not ``suggestion_log_service``'s colon-joined implementation --
``BL-134``), matching what ``EngineV2``/``OutfitPortfolioService`` already
compute for the same ``item_ids``.

Never raises just because the wardrobe is small/empty -- ``generate_portfolio``'s
own graceful degradation (an empty/short ``portfolio``) is inherited
unmodified; payload construction degrades to a shorter or empty ``items``
list, never an exception.
"""

from __future__ import annotations

from typing import Any

from adapters.interfaces import (
    IOutfitRepository,
    ISuggestionRailsRepository,
    IWardrobeRepository,
    SuggestionRailUpsert,
)
from ai.ports.interfaces import StylePreferencesInput
from services.engine_v2 import ENGINE_VERSION, EngineV2
from services.engine_v2_portfolio import compute_outfit_fingerprint
from services.engine_v2_types import PortfolioCandidate
from services.garment_registry_adapter import GarmentRegistryAdapter
from services.ist_window import ist_today
from services.occasion_normalizer import OccasionNormalizer
from services.occasion_resolution import resolve_occasion_input
from services.suggestion_rails_query import build_never_tried_pairs, build_not_yet_worn
from services.wardrobe_fetch import fetch_wardrobe_for_styling

# (design doc's "Engine call parameters for the precompute job") The exact
# same fallback string OutfitPortfolioService._resolve_occasion degrades to
# for an unresolvable occasion -- a "sensible default", not a
# weekday-frequency inference.
_PRECOMPUTE_OCCASION = "everyday"

# An existing, already-supported generate_portfolio kwarg (SS-039's effort
# tiers), widened from the engine's own (5, 8) default so ONE call yields
# enough candidates to slice into both todays_picks and newest_pieces.
_PORTFOLIO_SIZE_RANGE: tuple[int, int] = (15, 20)

# Rail slice sizes (product-shaped values, adjustable, not load-bearing).
_TODAYS_PICKS_LIMIT = 5
_NEWEST_PIECES_ANCHOR_LIMIT = 5
_NEWEST_PIECES_LIMIT = 5
_NEVER_TRIED_PAIRS_LIMIT = 10
_NOT_YET_WORN_LIMIT = 10


def _sort_key_created_at_then_id(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("created_at") or ""), str(row.get("id")))


class RailPrecomputeService:
    def __init__(
        self,
        *,
        engine: EngineV2,
        wardrobe_repo: IWardrobeRepository,
        outfit_repo: IOutfitRepository,
        garment_registry: GarmentRegistryAdapter,
        rails_repo: ISuggestionRailsRepository,
        occasion_normalizer: OccasionNormalizer,
    ) -> None:
        self._engine = engine
        self._wardrobe_repo = wardrobe_repo
        self._outfit_repo = outfit_repo
        self._garment_registry = garment_registry
        self._rails_repo = rails_repo
        self._occasion_normalizer = occasion_normalizer

    async def recompute_all_rails(self, *, jwt: str, user_id: str) -> None:
        occasion_input = await resolve_occasion_input(
            _PRECOMPUTE_OCCASION, jwt=jwt, occasion_normalizer=self._occasion_normalizer
        )
        wardrobe_by_id = await fetch_wardrobe_for_styling(
            jwt=jwt, user_id=user_id, wardrobe_repo=self._wardrobe_repo
        )
        preferences = await self._resolve_preferences(jwt=jwt, user_id=user_id)

        # The ONE engine call this whole job makes -- sliced two ways below.
        engine_result = await self._engine.generate_portfolio(
            list(wardrobe_by_id.values()),
            occasion_input,
            jwt=jwt,
            user_id=user_id,
            as_of=ist_today(),
            style_preferences=preferences,
            portfolio_size_range=_PORTFOLIO_SIZE_RANGE,
        )

        rail_rows = await self._wardrobe_repo.get_items_for_rails(jwt=jwt, user_id=user_id)

        await self._garment_registry.refresh()
        previously_paired = await self._outfit_repo.get_item_ids_for_user(jwt=jwt, user_id=user_id)

        never_tried_pairs = build_never_tried_pairs(
            rail_rows,
            garment_lookup=self._garment_registry.get_garment_attributes,
            previously_paired_item_ids=previously_paired,
            limit=_NEVER_TRIED_PAIRS_LIMIT,
        )
        not_yet_worn = build_not_yet_worn(rail_rows, limit=_NOT_YET_WORN_LIMIT)

        rows_by_id = {str(row["id"]): row for row in rail_rows}
        image_info = await self._fetch_image_info(
            jwt=jwt,
            engine_portfolio=engine_result.portfolio,
            never_tried_pairs=never_tried_pairs,
            not_yet_worn=not_yet_worn,
        )

        def snapshot(item_id: str) -> dict[str, Any]:
            entry: dict[str, Any] = {"item_id": item_id}
            row = rows_by_id.get(item_id)
            if row is not None:
                entry["category"] = row.get("category")
                entry["color_primary"] = row.get("color_primary")
            info = image_info.get(item_id)
            if info is not None:
                entry["thumbnail_url"] = (
                    info.get("thumbnail_url") or info.get("image_clean_url") or info.get("image_url")
                )
            return entry

        todays_picks_payload = self._build_engine_payload(
            engine_result.portfolio[:_TODAYS_PICKS_LIMIT], snapshot
        )
        newest_pieces_payload = self._build_newest_pieces_payload(
            rail_rows, engine_result.portfolio, snapshot
        )
        never_tried_pairs_payload = {
            "items": [
                {"item_ids": [top_id, bottom_id], "items": [snapshot(top_id), snapshot(bottom_id)]}
                for top_id, bottom_id in never_tried_pairs
            ]
        }
        not_yet_worn_payload = {
            "items": [
                {"item_ids": [item_id], "items": [snapshot(item_id)]} for item_id in not_yet_worn
            ]
        }

        await self._rails_repo.upsert_rails(
            jwt=jwt,
            user_id=user_id,
            rails=[
                SuggestionRailUpsert(
                    rail_key="todays_picks",
                    engine_version=ENGINE_VERSION,
                    payload=todays_picks_payload,
                ),
                SuggestionRailUpsert(
                    rail_key="newest_pieces",
                    engine_version=ENGINE_VERSION,
                    payload=newest_pieces_payload,
                ),
                SuggestionRailUpsert(
                    rail_key="never_tried_pairs",
                    engine_version=None,
                    payload=never_tried_pairs_payload,
                ),
                SuggestionRailUpsert(
                    rail_key="not_yet_worn",
                    engine_version=None,
                    payload=not_yet_worn_payload,
                ),
            ],
        )

    async def _resolve_preferences(self, *, jwt: str, user_id: str) -> StylePreferencesInput:
        raw = await self._wardrobe_repo.get_style_preferences(jwt=jwt, user_id=user_id)
        if not raw:
            return StylePreferencesInput()
        try:
            return StylePreferencesInput.model_validate(raw)
        except Exception:  # noqa: BLE001 -- malformed preferences degrade, never fail the job
            return StylePreferencesInput()

    async def _fetch_image_info(
        self,
        *,
        jwt: str,
        engine_portfolio: list[PortfolioCandidate],
        never_tried_pairs: list[tuple[str, str]],
        not_yet_worn: list[str],
    ) -> dict[str, dict[str, Any]]:
        all_ids: set[str] = set()
        for pc in engine_portfolio:
            all_ids.update(pc.candidate.item_ids)
        for top_id, bottom_id in never_tried_pairs:
            all_ids.add(top_id)
            all_ids.add(bottom_id)
        all_ids.update(not_yet_worn)
        if not all_ids:
            return {}
        return await self._wardrobe_repo.get_items_image_info_bulk(
            jwt=jwt, item_ids=list(all_ids)
        )

    def _build_engine_payload(
        self, portfolio_candidates: list[PortfolioCandidate], snapshot: Any
    ) -> dict[str, Any]:
        items = []
        for pc in portfolio_candidates:
            item_ids = list(pc.candidate.item_ids)
            items.append(
                {
                    "outfit_fingerprint": compute_outfit_fingerprint(item_ids),
                    "total_score": pc.candidate.total_score,
                    "item_ids": item_ids,
                    "items": [snapshot(item_id) for item_id in item_ids],
                }
            )
        return {"items": items}

    def _build_newest_pieces_payload(
        self,
        rail_rows: list[dict[str, Any]],
        engine_portfolio: list[PortfolioCandidate],
        snapshot: Any,
    ) -> dict[str, Any]:
        anchor_rows = sorted(rail_rows, key=_sort_key_created_at_then_id, reverse=True)
        anchor_ids = {str(row["id"]) for row in anchor_rows[:_NEWEST_PIECES_ANCHOR_LIMIT]}

        matching = [
            pc for pc in engine_portfolio if set(pc.candidate.item_ids) & anchor_ids
        ]
        matching_sorted = sorted(matching, key=lambda pc: -pc.candidate.total_score)
        return self._build_engine_payload(matching_sorted[:_NEWEST_PIECES_LIMIT], snapshot)
