"""Supabase-backed ``ISuggestionNarrationCacheRepository`` implementation
(SS-020).

ALWAYS uses ``service_role`` (mirrors ``SupabaseAppConfigRepository``/
``SupabaseSuggestionLogRepository`` precedent) -- ``suggestion_narration_cache``
has NO ``user_id`` column at all, by design (the structural half of "not
reversible into another user's wardrobe"; see migration ``019``'s own
docstring). There is no caller to scope an anon+JWT client to, and RLS on
this table is default-deny for every client role -- only ``service_role``
can read or write it at all.

**NOTHING ON THIS CLASS MAY RAISE** (the port's own contract) -- every
method wraps its whole body in ``try/except Exception``, logs, and returns
``None``/no-ops on any failure. A cache failure degrades to "always call the
LLM," never to a failed suggestion request.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import CachedNarration, ISuggestionNarrationCacheRepository

logger = logging.getLogger(__name__)


async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    # SERVICE_ROLE, not anon+JWT -- see module docstring.
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)


class SupabaseSuggestionNarrationCacheRepository(ISuggestionNarrationCacheRepository):
    """Real DB access for ``suggestion_narration_cache``."""

    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        try:
            client = await _client()
            response = (
                await client.table("suggestion_narration_cache")
                .select("narrations, language, expires_at")
                .eq("signature_hash", signature_hash)
                .limit(1)
                .execute()
            )
            rows = cast(list[dict[str, Any]], response.data or [])
            if not rows:
                return None
            row = rows[0]

            expires_at_raw = row.get("expires_at")
            if expires_at_raw is not None:
                expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
                if expires_at <= datetime.now(UTC):
                    return None  # expired -- treated as a miss, not an error

            raw_narrations = cast(dict[str, Any], row.get("narrations") or {})
            narrations_by_signature_index = {
                int(index_str): str(rationale) for index_str, rationale in raw_narrations.items()
            }

            # Best-effort hit-count increment -- diagnostic only, never
            # blocks the read, never allowed to turn a real cache hit into
            # an apparent failure.
            try:
                await client.table("suggestion_narration_cache").update(
                    {"hit_count": int(row.get("hit_count", 0) or 0) + 1}
                ).eq("signature_hash", signature_hash).execute()
            except Exception:  # noqa: BLE001 -- diagnostic only
                pass

            return CachedNarration(
                narrations_by_signature_index=narrations_by_signature_index,
                language=str(row.get("language", "en")),
            )
        except Exception as exc:  # noqa: BLE001 -- MUST NEVER RAISE
            logger.warning(
                "suggestion_narration_cache_get_failed",
                extra={"signature_hash": signature_hash, "error": str(exc)},
            )
            return None

    async def put(
        self,
        *,
        signature_hash: str,
        occasion_key: str,
        engine_version: str,
        narrations_by_signature_index: dict[int, str],
        language: str,
        ttl_seconds: int,
    ) -> None:
        try:
            client = await _client()
            expires_at = datetime.now(UTC) + timedelta(seconds=max(ttl_seconds, 1))
            payload: dict[str, Any] = {
                "signature_hash": signature_hash,
                "occasion_key": occasion_key,
                "engine_version": engine_version,
                "language": language,
                "narrations": {
                    str(index): rationale
                    for index, rationale in narrations_by_signature_index.items()
                },
                "expires_at": expires_at.isoformat(),
            }
            await client.table("suggestion_narration_cache").upsert(
                payload, on_conflict="signature_hash"
            ).execute()
        except Exception as exc:  # noqa: BLE001 -- MUST NEVER RAISE
            logger.warning(
                "suggestion_narration_cache_put_failed",
                extra={"signature_hash": signature_hash, "error": str(exc)},
            )
