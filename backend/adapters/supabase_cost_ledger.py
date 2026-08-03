"""``SupabaseCostLedger(ICostLedger)`` -- ``service_role`` writes to
``ai_cost_ledger`` (SS-029 design §3.5).

Deliberate deviation from this repo's "never ``service_role``" convention
for every other ``adapters/`` repository, following the SAME precedent
``SupabaseAppConfigRepository`` already established (SS-026): this data is
accounting data ABOUT a user, not authored BY them, RLS is default-deny for
every non-``service_role`` role on this table, and the write happens in a
``BackgroundTasks`` callback that can outlive the caller's short-lived JWT
-- there may be no usable session at all by the time this runs. See
``ai_cost_ledger``'s own migration (``012_ai_cost_ledger.sql``) for the RLS
policy this relies on.

``record()`` MUST NEVER RAISE (``ICostLedger``'s contract) -- wraps the
write in ``try/except Exception``, logs ``ledger_write_failed`` at ERROR
(Sentry-visible per SS-009/SS-026), and returns. An unbilled call is better
than a broken feature (design §4.3).
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import CostLedgerEntry, ICostLedger

logger = logging.getLogger(__name__)


async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    # SERVICE_ROLE, not anon+JWT -- see module docstring.
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)


class SupabaseCostLedger(ICostLedger):
    async def record(self, entry: CostLedgerEntry) -> None:
        try:
            client = await _client()
            await client.table("ai_cost_ledger").insert(
                {
                    "user_id": entry.user_id,
                    "request_id": entry.request_id,
                    "provider": entry.provider,
                    "model": entry.model,
                    "feature": entry.feature,
                    "tokens_in": entry.tokens_in,
                    "tokens_out": entry.tokens_out,
                    "cost_micropaise": entry.cost_micropaise,
                    "latency_ms": entry.latency_ms,
                    "cache_hit": entry.cache_hit,
                    "pricing_status": entry.pricing_status,
                    "price_effective_from": entry.price_effective_from,
                    "unit_price_snapshot": entry.unit_price_snapshot,
                    "attempt": entry.attempt,
                    "outcome": entry.outcome,
                }
            ).execute()
        except Exception as exc:  # noqa: BLE001 -- never raise, see module docstring
            logger.error(
                "ledger_write_failed",
                extra={
                    "user_id": entry.user_id,
                    "request_id": entry.request_id,
                    "feature": entry.feature,
                    "error": str(exc),
                },
            )

    async def breakdown(
        self, *, user_id: str, since: date, until: date
    ) -> list[dict[str, Any]]:
        """Reads the ``ai_cost_breakdown`` view. May raise -- an
        operator/BI read path, never on any user request path."""
        client = await _client()
        response = (
            await client.table("ai_cost_breakdown")
            .select("*")
            .eq("user_id", user_id)
            .gte("ist_date", since.isoformat())
            .lte("ist_date", until.isoformat())
            .execute()
        )
        return cast(list[dict[str, Any]], response.data or [])
