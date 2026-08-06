"""Supabase-backed ``IFabricRegistryRepository`` implementation (SS-038).

Same ``service_role`` justification as ``garment_registry_repository.py``
(reference data, ``authenticated_read_fabrics`` RLS policy has no per-user
ownership -- see ``016_pattern_fabric_registries.sql``).

No TTL-cache class needed, unlike ``GarmentRegistryAdapter`` -- ``fabrics``
has 11 seeded rows, near-zero write frequency, and ``engine_v2.py`` fetches
it once per ``generate_portfolio()`` call (not per-item inside the hot
scoring loop). A plain per-request fetch is cheap and needs none of
``GarmentRegistryAdapter``'s cross-request caching sophistication, which
exists specifically because ``get_garment_attributes`` is called once per
item INSIDE the O(pairs) scoring loop.
"""

from __future__ import annotations

import os
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import FabricAttributes, IFabricRegistryRepository


async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    # SERVICE_ROLE, not anon+JWT -- see module docstring.
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)


def _to_attributes(raw: dict[str, Any]) -> FabricAttributes:
    season_affinity = raw.get("season_affinity")
    return FabricAttributes(
        key=str(raw["key"]),
        weight=raw.get("weight"),
        breathability=raw.get("breathability"),
        season_affinity=tuple(season_affinity) if season_affinity else None,
    )


class SupabaseFabricRegistryRepository(IFabricRegistryRepository):
    """Real DB access for ``fabrics``. Constructor-injected into
    ``EngineV2`` behind the ``IFabricRegistryRepository`` port."""

    async def fetch_all(self) -> dict[str, FabricAttributes]:
        client = await _client()
        response = (
            await client.table("fabrics")
            .select("key, weight, breathability, season_affinity")
            .eq("is_active", True)
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        return {str(row["key"]): _to_attributes(row) for row in rows}
