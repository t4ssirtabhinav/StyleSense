"""Supabase-backed ``ISuggestionLogRepository`` implementation (SS-033).

Mirrors ``SupabaseAppConfigRepository`` exactly: ``service_role`` client via
``acreate_client``, no ``.postgrest.auth(jwt)`` -- the service-role key IS
the credential. ``suggestion_sessions``/``suggestion_impressions``/
``suggestion_outcomes`` have NO write policy for any client role at all
(``013_suggestion_impressions.sql``'s design §3.5), so ``anon``/
``authenticated`` writes are denied by RLS regardless of what key is used --
``service_role`` bypassing RLS is the only way this class can write at all.
This is the SECOND port in this file to deviate from the "never
service_role" convention (see ``app_config_repository.py``'s docstring for
the first), for the same underlying reason: accounting-style data ABOUT a
user, not authored BY them, and the write can outlive the caller's JWT (it
runs inside a ``BackgroundTasks`` callback after the response was sent).

**NOTHING ON THIS CLASS MAY RAISE** (the port's own contract, design §5.4).
Every method wraps its whole body in ``try/except Exception``, logs, and
returns ``None``/``[]`` on any failure -- a logging failure must never fail
the user's suggestion request.

``user_id`` is sent on the impression insert payload even though a
``BEFORE INSERT`` trigger (``013``'s ``suggestion_impression_set_user_id``)
unconditionally overwrites it -- a self-describing insert that keeps the
column's ``NOT NULL`` satisfiable if the trigger is ever dropped (design
§3.5). ``suggestion_outcomes`` inserts carry NO ``user_id`` at all --
``SuggestionOutcomeLog`` has no such field, since an outcome's owner is only
knowable via its impression, which is exactly what
``suggestion_outcome_set_user_id`` derives server-side.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import (
    ImpressionRef,
    ISuggestionLogRepository,
    SuggestionImpressionLog,
    SuggestionOutcomeLog,
    SuggestionSessionLog,
)

logger = logging.getLogger(__name__)

# design §5.2 item 6 -- a client clock ahead of the server must not silently
# reorder the canonical outcome sequence (COALESCE(client_occurred_at,
# created_at), created_at, id).
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)

# Substrings of a postgrest-py APIError's message/code that identify a
# unique-violation on suggestion_outcomes' partial dedupe index -- a
# retried write hitting this is success-already-recorded, not a failure
# (design §3.4/§5.1's log_outcome contract).
_DEDUPE_CONFLICT_MARKERS = ("23505", "duplicate key", "uq_suggestion_outcomes_dedupe")


async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    # SERVICE_ROLE, not anon+JWT -- see module docstring for why this is a
    # deliberate exception to most of this file's siblings' convention.
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)


def _session_payload(session: SuggestionSessionLog) -> dict[str, Any]:
    return {
        "user_id": session.user_id,
        "occasion": session.occasion,
        "weather_data": session.weather_data,
        "tier": session.tier,
        "effort_tier": session.effort_tier,
        "engine_version": session.engine_version,
        "config_snapshot_hash": session.config_snapshot_hash,
        "candidate_count": session.candidate_count,
        "cache_key": session.cache_key,
        "request_id": session.request_id,
        "latency_ms": session.latency_ms,
        "cost_incurred": session.cost_incurred,
        "zero_cost_reason": session.zero_cost_reason,
    }


def _impression_payload(
    session_id: str, user_id: str, impression: SuggestionImpressionLog
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        # Overwritten by trg_suggestion_impressions_set_user_id -- sent
        # anyway (self-describing insert, see module docstring).
        "user_id": user_id,
        "rank": impression.rank,
        "item_ids": impression.item_ids,
        "outfit_fingerprint": impression.outfit_fingerprint,
        "total_score": impression.total_score,
        "rule_scores": impression.rule_scores,
        "gap_flags": impression.gap_flags,
        "is_exploration": impression.is_exploration,
        "strategy": impression.strategy,
    }


def _clamp_client_occurred_at(raw: str | None) -> str | None:
    """>5 minutes in the future is clamped to now() and logged at WARNING
    (design §5.2 item 6). An unparseable value degrades to None (the column
    is nullable; ordering then falls back to created_at) rather than
    failing the write."""
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        logger.warning(
            "suggestion_outcome_client_occurred_at_unparseable",
            extra={"raw": raw, "error": str(exc)},
        )
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if parsed - now > CLOCK_SKEW_TOLERANCE:
        logger.warning(
            "suggestion_outcome_clock_skew",
            extra={"client_occurred_at": raw, "clamped_to": now.isoformat()},
        )
        return now.isoformat()
    return parsed.isoformat()


def _is_dedupe_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker.lower() in text for marker in _DEDUPE_CONFLICT_MARKERS)


class SupabaseSuggestionLogRepository(ISuggestionLogRepository):
    """Real DB access for ``suggestion_sessions``/``suggestion_impressions``/
    ``suggestion_outcomes``. Constructor-injected into
    ``SuggestionLogService`` behind the ``ISuggestionLogRepository`` port."""

    async def log_session(
        self,
        session: SuggestionSessionLog,
        impressions: Sequence[SuggestionImpressionLog],
    ) -> str | None:
        try:
            client = await _client()
        except Exception as exc:
            logger.error("suggestion_session_log_failed", extra={"error": str(exc)})
            return None

        session_id: str | None = None
        try:
            response = (
                await client.table("suggestion_sessions")
                .insert(_session_payload(session))
                .execute()
            )
            rows = cast(list[dict[str, Any]], response.data or [])
            if not rows:
                logger.error(
                    "suggestion_session_log_failed",
                    extra={"reason": "insert returned no row", "user_id": session.user_id},
                )
                return None
            session_id = str(rows[0]["id"])
        except Exception as exc:
            logger.error(
                "suggestion_session_log_failed",
                extra={"user_id": session.user_id, "error": str(exc)},
            )
            return None

        if not impressions:
            return session_id

        try:
            payload = [
                _impression_payload(session_id, session.user_id, impression)
                for impression in impressions
            ]
            await client.table("suggestion_impressions").insert(payload).execute()
        except Exception as exc:
            # The session row is real and the cost monitor must still see
            # it -- do NOT attempt to delete it "to keep things tidy"
            # (design §5.2 item 4: a partial log is more truthful than a
            # deleted one, and a delete could fail too).
            logger.error(
                "suggestion_impression_log_failed",
                extra={"session_id": session_id, "error": str(exc)},
            )
        return session_id

    async def log_outcome(self, outcome: SuggestionOutcomeLog) -> str | None:
        try:
            client = await _client()
            payload = {
                "impression_id": outcome.impression_id,
                "outcome_type": outcome.outcome_type,
                "outfit_id": outcome.outfit_id,
                "dedupe_key": outcome.dedupe_key,
                "client_occurred_at": _clamp_client_occurred_at(outcome.client_occurred_at),
                "metadata": outcome.metadata,
            }
            response = await client.table("suggestion_outcomes").insert(payload).execute()
            rows = cast(list[dict[str, Any]], response.data or [])
            if not rows:
                logger.error(
                    "suggestion_outcome_log_failed",
                    extra={
                        "reason": "insert returned no row",
                        "impression_id": outcome.impression_id,
                    },
                )
                return None
            return str(rows[0]["id"])
        except Exception as exc:
            if _is_dedupe_conflict(exc):
                logger.info(
                    "suggestion_outcome_dedupe_conflict",
                    extra={
                        "impression_id": outcome.impression_id,
                        "dedupe_key": outcome.dedupe_key,
                    },
                )
            else:
                logger.error(
                    "suggestion_outcome_log_failed",
                    extra={"impression_id": outcome.impression_id, "error": str(exc)},
                )
            return None

    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict[str, Any]]:
        try:
            client = await _client()
            response = (
                await client.table("suggestion_impressions")
                .select("*")
                .eq("user_id", user_id)
                .gte("created_at", since.isoformat())
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return cast(list[dict[str, Any]], response.data or [])
        except Exception as exc:
            logger.warning(
                "suggestion_recent_impressions_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return []

    async def update_session_outcome(
        self,
        *,
        session_id: str,
        cost_incurred: bool,
        request_id: str | None,
        latency_ms: int | None,
    ) -> None:
        """(SS-020) Best-effort update of a session row already written by
        ``EngineV2._log_session`` -- reflects the narration leg's real
        outcome (cache hit / LLM call / degrade) without reopening Engine
        v2's own "no AI provider calls" boundary. MUST NEVER RAISE."""
        try:
            client = await _client()
            payload: dict[str, Any] = {"cost_incurred": cost_incurred}
            if request_id is not None:
                payload["request_id"] = request_id
            if latency_ms is not None:
                payload["latency_ms"] = latency_ms
            if cost_incurred:
                # cost_incurred=True clears the earlier rules_only reason --
                # the CHECK constraint pairing cost_incurred/zero_cost_reason
                # (design §6.3) requires this, not just good hygiene.
                payload["zero_cost_reason"] = None
            await client.table("suggestion_sessions").update(payload).eq(
                "id", session_id
            ).execute()
        except Exception as exc:
            logger.warning(
                "suggestion_session_outcome_update_failed",
                extra={"session_id": session_id, "error": str(exc)},
            )

    async def find_impression(self, *, session_id: str, rank: int) -> ImpressionRef | None:
        """(SS-023) Resolves the ``(session_id, rank)`` UNIQUE constraint via
        an embedded PostgREST select that also pulls the parent
        ``suggestion_sessions.occasion`` in the same round-trip (the FK
        ``suggestion_impressions.session_id -> suggestion_sessions.id``
        makes the embed resolvable). MUST NEVER RAISE -- not-found and any
        transport/parse failure both degrade to ``None``, indistinguishable
        by contract (the caller must 404 identically for both, design §3)."""
        try:
            client = await _client()
            response = (
                await client.table("suggestion_impressions")
                .select(
                    "id,user_id,session_id,rank,item_ids,outfit_fingerprint,total_score,"
                    "is_exploration,suggestion_sessions(occasion)"
                )
                .eq("session_id", session_id)
                .eq("rank", rank)
                .limit(1)
                .execute()
            )
            rows = cast(list[dict[str, Any]], response.data or [])
            if not rows:
                return None
            row = rows[0]
            session_row = row.get("suggestion_sessions") or {}
            occasion = session_row.get("occasion") if isinstance(session_row, dict) else None
            return ImpressionRef(
                impression_id=str(row["id"]),
                user_id=str(row["user_id"]),
                session_id=str(row["session_id"]),
                rank=int(row["rank"]),
                item_ids=list(row.get("item_ids") or []),
                outfit_fingerprint=str(row["outfit_fingerprint"]),
                total_score=float(row["total_score"]),
                is_exploration=bool(row.get("is_exploration", False)),
                occasion=occasion,
            )
        except Exception as exc:
            logger.warning(
                "suggestion_find_impression_failed",
                extra={"session_id": session_id, "rank": rank, "error": str(exc)},
            )
            return None
