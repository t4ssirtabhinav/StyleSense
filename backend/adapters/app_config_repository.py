"""Supabase-backed ``IAppConfigRepository`` implementation (SS-026).

**Deliberate deviation from this repo's established convention.** Every
other ``adapters/`` repository (``SupabaseWardrobeRepository``,
``SupabaseOccasionRepository``) is documented "never ``service_role`` --
scope to the caller's own JWT", because that data is per-user and RLS's
``auth.uid() = user_id`` policies are a real defense-in-depth backstop
against an application bug passing the wrong ``user_id``. ``app_config`` is
categorically different: it is not user data, there is no caller to scope
it to, and the ticket's own AC requires reads to be ``service_role``-only
by default (see ``supabase/migrations/010_app_config.sql``'s RLS policy --
only an explicit, per-row ``scope = 'client_visible'`` opt-in is readable by
``authenticated`` at all). Using the anon key + a caller JWT here would be
actively wrong: an unauthenticated background task has no JWT to pass, and
would only ever see the empty ``client_visible`` subset regardless.

This is compliant with CLAUDE.md's Security section ("Never use
``service_role`` key in client-side code" -- this is backend-only; "All
user data queries MUST use authenticated Supabase client" -- ``app_config``
is not user data), but IS a new pattern in ``adapters/``, called out
explicitly here rather than silently introduced. See design §3.4.
"""

from __future__ import annotations

import os
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import IAppConfigRepository


async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    # SERVICE_ROLE, not anon+JWT -- see module docstring for why this is a
    # deliberate exception to this file's siblings' convention, not a bug.
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)


class SupabaseAppConfigRepository(IAppConfigRepository):
    """Real DB access for ``app_config``. Constructor-injected into
    ``AppConfigService`` behind the ``IAppConfigRepository`` port."""

    async def fetch_all(self) -> dict[str, Any]:
        client = await _client()
        response = await client.table("app_config").select("key, value").execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        return {str(row["key"]): row["value"] for row in rows}
