"""Supabase-backed ``ISuggestionRailsRepository`` implementation (SS-048).

Follows ``outfit_repository.py``'s pattern exactly: a fresh RLS-scoped async
Supabase client per call, built from the anon key and authenticated with the
**caller's own bearer token** via ``postgrest.auth(jwt)`` -- never
``service_role``. ``suggestion_rails`` keeps its ``user_owns_rails`` ``FOR
ALL`` policy (migration ``024``) as the real enforcement.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import ISuggestionRailsRepository, SuggestionRailRow, SuggestionRailUpsert


async def _client_for(jwt: str) -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    client = await acreate_client(url, anon_key)
    client.postgrest.auth(jwt)
    return client


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class SupabaseSuggestionRailsRepository(ISuggestionRailsRepository):
    """Real DB access for ``suggestion_rails``. Constructor-injected into
    ``RailPrecomputeService``/the ``suggestion_rails`` router behind the
    ``ISuggestionRailsRepository`` port."""

    async def upsert_rails(
        self, *, jwt: str, user_id: str, rails: list[SuggestionRailUpsert]
    ) -> None:
        if not rails:
            return
        client = await _client_for(jwt)
        payload = [
            {
                "user_id": user_id,
                "rail_key": rail.rail_key,
                "engine_version": rail.engine_version,
                "payload": rail.payload,
                "computed_at": datetime.now().astimezone().isoformat(),
            }
            for rail in rails
        ]
        await (
            client.table("suggestion_rails")
            .upsert(payload, on_conflict="user_id,rail_key")
            .execute()
        )

    async def get_rails(self, *, jwt: str, user_id: str) -> list[SuggestionRailRow]:
        client = await _client_for(jwt)
        response = (
            await client.table("suggestion_rails")
            .select("rail_key, computed_at, engine_version, payload")
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        return [
            SuggestionRailRow(
                rail_key=str(row["rail_key"]),
                computed_at=_parse_timestamp(row["computed_at"]),
                engine_version=row.get("engine_version"),
                payload=cast(dict[str, Any], row.get("payload") or {"items": []}),
            )
            for row in rows
        ]

    async def get_most_recent_computed_at(self, *, jwt: str, user_id: str) -> datetime | None:
        client = await _client_for(jwt)
        response = (
            await client.table("suggestion_rails")
            .select("computed_at")
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            return None
        return _parse_timestamp(rows[0]["computed_at"])
