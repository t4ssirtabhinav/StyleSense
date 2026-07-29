"""Supabase-backed ``IOccasionRepository`` implementation (SS-025).

Follows ``wardrobe_repository.py``'s pattern exactly: a fresh RLS-scoped
async Supabase client per call, built from the anon key and authenticated
with the **caller's own bearer token** via ``postgrest.auth(jwt)`` --
**never** ``service_role``. ``occasions``/``occasion_aliases`` are reference
tables whose RLS policy is ``auth.role() = 'authenticated'``; reading them
with the caller's token keeps that policy in the loop rather than routing
around it.

Only ``is_active = true`` rows are requested. A deactivated occasion is
deliberately absent from the Gemini prompt vocabulary and from the mobile
pickers -- items already carrying it keep their tag (nothing rewrites
``occasion_tags`` on deactivation), and it still normalises correctly on a
later write because the DB function reads the table directly, not this
snapshot.
"""

from __future__ import annotations

import os
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import IOccasionRepository, OccasionRegistrySnapshot


async def _client_for(jwt: str) -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    client = await acreate_client(url, anon_key)
    client.postgrest.auth(jwt)
    return client


class SupabaseOccasionRepository(IOccasionRepository):
    """Real DB access for the occasion registry. Constructor-injected into
    ``OccasionNormalizer`` behind the ``IOccasionRepository`` port."""

    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        client = await _client_for(jwt)

        occasions_response = (
            await client.table("occasions")
            .select("key, label, badge_color, kind, parent_key, sort_order")
            .eq("is_active", True)
            .order("sort_order", desc=False)
            .execute()
        )
        aliases_response = (
            await client.table("occasion_aliases").select("alias, occasion_key").execute()
        )

        occasion_rows = cast(list[dict[str, Any]], occasions_response.data or [])
        alias_rows = cast(list[dict[str, Any]], aliases_response.data or [])

        return OccasionRegistrySnapshot(
            keys=tuple(str(row["key"]) for row in occasion_rows),
            aliases={str(row["alias"]): str(row["occasion_key"]) for row in alias_rows},
            labels={str(row["key"]): str(row["label"]) for row in occasion_rows},
            badge_colors={str(row["key"]): str(row["badge_color"]) for row in occasion_rows},
        )
