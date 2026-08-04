"""Supabase-backed ``IWearHistoryRepository`` implementation (SS-035).

Follows ``occasion_repository.py``'s pattern exactly: a fresh RLS-scoped
async Supabase client per call, built from the anon key and authenticated
with the **caller's own bearer token** via ``postgrest.auth(jwt)`` --
**never** ``service_role``. ``public.wear_recency()`` is ``SECURITY
INVOKER`` (the default, design §3.7) precisely so this client's RLS
(``user_owns_item_wears``, ``006_wardrobe_item_wears.sql:38-41``) stays in
force -- reading with the caller's own token keeps that policy in the loop
rather than routing around it.

**NOTHING ON THIS CLASS MAY RAISE** (the port's own contract). 'No history'
degrades to 'no novelty penalty', never to a failed suggestion request --
mirrors ``SupabaseSuggestionLogRepository.recent_impressions``'s posture.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import IWearHistoryRepository, WearRecency

logger = logging.getLogger(__name__)


async def _client_for(jwt: str) -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    client = await acreate_client(url, anon_key)
    client.postgrest.auth(jwt)
    return client


def _parse_date(raw: Any) -> date | None:
    """``wear_recency()`` returns Postgres DATE columns, which PostgREST
    serialises as 'YYYY-MM-DD' strings. A malformed/unexpected value
    degrades to None rather than raising -- this class must never raise."""
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _to_wear_recency(row: dict[str, Any]) -> WearRecency:
    return WearRecency(
        item_id=str(row["item_id"]),
        last_worn_on=_parse_date(row.get("last_worn_on")),
        last_worn_on_for_occasion=_parse_date(row.get("last_worn_on_for_occasion")),
        # Never None -- the port's own contract (a caller must not have to
        # None-arithmetic this), and wear_recency()'s COUNT(*) FILTER
        # already returns 0 rather than NULL for "no match".
        wears_for_occasion=int(row.get("wears_for_occasion") or 0),
    )


class SupabaseWearHistoryRepository(IWearHistoryRepository):
    """Real DB access for ``public.wear_recency()``. Constructor-injected
    behind the ``IWearHistoryRepository`` port -- no caller exists yet
    (BL-119); Engine v2 / SS-020 wires one in."""

    async def fetch_wear_recency(
        self, *, jwt: str, user_id: str, occasion_key: str | None = None
    ) -> list[WearRecency]:
        try:
            client = await _client_for(jwt)
            response = await client.rpc(
                "wear_recency",
                {"p_user_id": user_id, "p_occasion_key": occasion_key},
            ).execute()
            rows = cast(list[dict[str, Any]], response.data or [])
            return [_to_wear_recency(row) for row in rows]
        except Exception as exc:
            logger.error(
                "wear_recency_fetch_failed",
                extra={"user_id": user_id, "occasion_key": occasion_key, "error": str(exc)},
            )
            return []
