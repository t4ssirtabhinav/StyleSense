"""SS-023 -- ``OutfitOutcomeService``: the orchestrator behind
``POST /outfit-suggestions/outcome``.

One swipe = up to three writes across three tables with three different
access postures (design §3): ``outfits`` (JWT-scoped, user-authored
content), ``suggestion_outcomes`` (service_role, no client write policy by
deliberate design, accounting-style data), and -- only for the "Wore this
today" sub-feature (§6) -- ``wardrobe_item_wears`` (JWT-scoped).

**The load-bearing security check in this whole ticket:**
``ISuggestionLogRepository`` is ``service_role`` and bypasses RLS entirely,
so ``find_impression`` will happily return ANY user's impression. This
service MUST compare the returned ``ImpressionRef.user_id`` against the
JWT-derived caller ``user_id`` and refuse (``OutcomeNotFoundError``, mapped
by the router to a flat 404 -- never 403, which would be an enumeration
oracle over another user's session ids) BEFORE any write. Without this
comparison, the endpoint is a cross-tenant write primitive into the
personalisation corpus (design §3's full threat description).

``outfits.occasion`` is ALWAYS read from the impression's own session row
(``ImpressionRef.occasion``), never from anything the caller sent -- there
is deliberately no ``occasion`` field on the request model (design §7).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from adapters.interfaces import (
    IOutfitRepository,
    ISuggestionLogRepository,
    IWardrobeRepository,
    OutfitInsert,
    SuggestionOutcomeLog,
)
from services.ist_window import ist_today

logger = logging.getLogger(__name__)

OutcomeType = Literal["saved", "dismissed", "worn", "shared"]

# Outcome types that must ensure an `outfits` row exists (idempotent insert
# keyed on (user_id, outfit_fingerprint)). 'dismissed' deliberately never
# writes an outfits row (test plan item 5).
_OUTCOME_TYPES_THAT_SAVE: frozenset[str] = frozenset({"saved", "worn", "shared"})


class OutcomeNotFoundError(Exception):
    """(session_id, rank) does not resolve to an impression, OR resolves to
    one owned by a different user -- deliberately indistinguishable by the
    caller (router maps both to a flat 404, never 403, design §3)."""


class OutfitOutcomeService:
    def __init__(
        self,
        *,
        suggestion_log_repo: ISuggestionLogRepository,
        outfit_repo: IOutfitRepository,
        wardrobe_repo: IWardrobeRepository,
    ) -> None:
        self._suggestion_log_repo = suggestion_log_repo
        self._outfit_repo = outfit_repo
        self._wardrobe_repo = wardrobe_repo

    async def record_outcome(
        self,
        *,
        user_id: str,
        jwt: str,
        session_id: str,
        rank: int,
        outcome_type: OutcomeType,
        client_occurred_at: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        impression = await self._suggestion_log_repo.find_impression(
            session_id=session_id, rank=rank
        )
        # Identical 404 for "not found" and "belongs to someone else" -- the
        # single most important line in this ticket (design §3).
        if impression is None or impression.user_id != user_id:
            raise OutcomeNotFoundError()

        outfit_id: str | None = None
        already_saved = False
        wear_already_logged_today = False

        if outcome_type in _OUTCOME_TYPES_THAT_SAVE:
            items_snapshot = await self._build_items_snapshot(
                jwt=jwt, user_id=user_id, item_ids=impression.item_ids
            )
            outfit_insert = OutfitInsert(
                user_id=user_id,
                item_ids=impression.item_ids,
                occasion=impression.occasion,  # server-derived, NEVER client-asserted (§7)
                name=name,
                ai_generated=True,
                session_id=impression.session_id,
                outfit_fingerprint=impression.outfit_fingerprint,
                items_snapshot=items_snapshot,
            )
            outfit_id, already_saved = await self._outfit_repo.insert_outfit(
                jwt=jwt, outfit=outfit_insert
            )

            if outcome_type == "worn":
                worn_on = ist_today().isoformat()
                inserted = await self._outfit_repo.insert_wear_rows(
                    jwt=jwt,
                    user_id=user_id,
                    item_ids=impression.item_ids,
                    worn_on=worn_on,
                    occasion_key=impression.occasion,
                    outfit_id=outfit_id,
                )
                wear_already_logged_today = not inserted

        outcome_log = SuggestionOutcomeLog(
            impression_id=impression.impression_id,
            outcome_type=outcome_type,
            outfit_id=outfit_id,
            client_occurred_at=client_occurred_at,
        )
        logged_id = await self._suggestion_log_repo.log_outcome(outcome_log)
        # A logging failure must NEVER lose the user's outfit -- the
        # `outfits` insert above already committed and is not rolled back
        # (test plan item 8).
        outcome_recorded = logged_id is not None

        return {
            "outfit_id": outfit_id,
            "outcome_recorded": outcome_recorded,
            # `already_saved` doubles for the wear-idempotency signal on a
            # 'worn' outcome (no separate field exists on
            # RecordOutcomeResponse, design §1) -- True when EITHER the
            # outfit row already existed OR (for 'worn') today's wear was
            # already logged. Documented here as a deliberate, minimal
            # reading of the one flag available, not an accidental overload.
            "already_saved": already_saved or wear_already_logged_today,
        }

    async def _build_items_snapshot(
        self, *, jwt: str, user_id: str, item_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Denormalised {item_id, category, color_primary, image_path} per
        item AT SAVE TIME (migration 020's column comment). Must tolerate a
        wardrobe fetch returning fewer rows than item_ids has entries (an
        item deleted between suggestion and swipe) -- write what resolved,
        leave the rest as {item_id, missing: True} (design edge cases)."""
        try:
            styling_rows = await self._wardrobe_repo.get_items_for_styling(
                jwt=jwt, user_id=user_id
            )
        except Exception as exc:  # noqa: BLE001 -- a snapshot-read failure must never fail the save
            logger.warning("outfit_outcome_styling_rows_failed", extra={"error": str(exc)})
            styling_rows = []
        by_id = {str(row.get("id")): row for row in styling_rows}

        try:
            image_info = await self._wardrobe_repo.get_items_image_info_bulk(
                jwt=jwt, item_ids=item_ids
            )
        except Exception as exc:  # noqa: BLE001 -- same posture
            logger.warning("outfit_outcome_image_info_failed", extra={"error": str(exc)})
            image_info = {}

        snapshot: list[dict[str, Any]] = []
        for item_id in item_ids:
            styling_row = by_id.get(item_id)
            info = image_info.get(item_id)
            if styling_row is None and info is None:
                snapshot.append({"item_id": item_id, "missing": True})
                continue
            entry: dict[str, Any] = {"item_id": item_id}
            if styling_row is not None:
                entry["category"] = styling_row.get("category")
                entry["color_primary"] = styling_row.get("color_primary")
            if info is not None:
                image_path = (
                    info.get("thumbnail_url") or info.get("image_clean_url") or info.get("image_url")
                )
                if image_path is not None:
                    entry["image_path"] = image_path
            snapshot.append(entry)
        return snapshot
