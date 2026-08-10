"""Supabase-backed ``IOutfitRepository`` implementation (SS-023).

Follows ``wardrobe_repository.py``'s pattern exactly: a fresh RLS-scoped
async Supabase client per call, built from the anon key and authenticated
with the **caller's own bearer token** via ``postgrest.auth(jwt)`` -- never
``service_role``. ``outfits`` and ``wardrobe_item_wears`` both keep their
existing ``FOR ALL``/``WITH CHECK`` "fully private to owner" RLS policies
(``001:168``, ``006:38-41``) as the real enforcement -- see design §3's
rejected-alternative note for why this deliberately does NOT mirror
``suggestion_log_repository.py``'s ``service_role`` posture.
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import IOutfitRepository, OutfitInsert

logger = logging.getLogger(__name__)

# Substrings of a postgrest-py APIError's message/code that identify a
# unique-violation on outfits' partial idempotent-save index
# (uq_outfits_user_fingerprint, migration 020) -- a retried swipe-right
# hitting this is success-already-recorded, not a failure. Mirrors
# suggestion_log_repository.py's own _DEDUPE_CONFLICT_MARKERS/
# _is_dedupe_conflict pattern.
_DEDUPE_CONFLICT_MARKERS = ("23505", "duplicate key", "uq_outfits_user_fingerprint")


async def _client_for(jwt: str) -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    client = await acreate_client(url, anon_key)
    client.postgrest.auth(jwt)
    return client


def _is_dedupe_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker.lower() in text for marker in _DEDUPE_CONFLICT_MARKERS)


def _outfit_payload(outfit: OutfitInsert) -> dict[str, Any]:
    return {
        "user_id": outfit.user_id,
        "name": outfit.name,
        "item_ids": outfit.item_ids,
        "occasion": outfit.occasion,
        "season": outfit.season,
        "ai_generated": outfit.ai_generated,
        "ai_reasoning": outfit.ai_reasoning,
        "session_id": outfit.session_id,
        "outfit_fingerprint": outfit.outfit_fingerprint,
        "engine_version": outfit.engine_version,
        "effort_tier": outfit.effort_tier,
        "reasoning_language": outfit.reasoning_language,
        "items_snapshot": outfit.items_snapshot,
    }


class SupabaseOutfitRepository(IOutfitRepository):
    """Real DB access for ``outfits``/``wardrobe_item_wears`` writes.
    Constructor-injected into ``OutfitOutcomeService`` behind the
    ``IOutfitRepository`` port."""

    async def insert_outfit(self, *, jwt: str, outfit: OutfitInsert) -> tuple[str, bool]:
        client = await _client_for(jwt)
        try:
            response = (
                await client.table("outfits").insert(_outfit_payload(outfit)).execute()
            )
            rows = cast(list[dict[str, Any]], response.data or [])
            if not rows:
                raise RuntimeError("outfits insert returned no row")
            return str(rows[0]["id"]), False
        except Exception as exc:
            if not _is_dedupe_conflict(exc):
                raise
            logger.info(
                "outfit_save_dedupe_conflict",
                extra={"user_id": outfit.user_id, "outfit_fingerprint": outfit.outfit_fingerprint},
            )
            existing = (
                await client.table("outfits")
                .select("id")
                .eq("user_id", outfit.user_id)
                .eq("outfit_fingerprint", outfit.outfit_fingerprint)
                .limit(1)
                .execute()
            )
            existing_rows = cast(list[dict[str, Any]], existing.data or [])
            if not existing_rows:
                # Should be unreachable (the conflict just proved the row
                # exists), but never invent an id -- surface the real error.
                raise RuntimeError(
                    "outfit dedupe conflict but no existing row found"
                ) from exc
            return str(existing_rows[0]["id"]), True

    async def insert_wear_rows(
        self,
        *,
        jwt: str,
        user_id: str,
        item_ids: list[str],
        worn_on: str,
        occasion_key: str | None,
        outfit_id: str,
    ) -> bool:
        client = await _client_for(jwt)
        payload = [
            {
                "item_id": item_id,
                "user_id": user_id,
                "worn_on": worn_on,
                "occasion_key": occasion_key,
                "outfit_id": outfit_id,
            }
            for item_id in item_ids
        ]
        if not payload:
            return False
        response = (
            await client.table("wardrobe_item_wears")
            .upsert(
                payload,
                on_conflict="item_id,worn_on,occasion_key",
                ignore_duplicates=True,
            )
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        return len(rows) > 0
