"""SS-028 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise AC #2 ("Router selects provider+model
from the app_config routing table; changing the table changes routing
WITHOUT A REDEPLOY") the same way
backend/scripts/ss026_verify_config_live_reload.py proved SS-026's own
live-reload AC: no unit test can honestly claim "without a redeploy",
that needs a real process, a real DB row flip, and the SAME process
observing the change on its next request.

Usage: `python -m scripts.ss028_verify_routing_live_reload` (from backend/,
with the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/
SUPABASE_ANON_KEY set, e.g. via `set -a && source ../.env && set +a`).

Never touches GEMINI_API_KEY/ANTHROPIC_API_KEY or makes a real provider
call -- this script only proves the ROUTING DECISION changes live; it
verifies via ``resolve_route()`` fed the real config-service snapshot, not
by spending real provider quota.
"""

from __future__ import annotations

import asyncio
import os

import httpx

from adapters.app_config_repository import SupabaseAppConfigRepository
from services.ai_routing_specs import AI_STYLING_ROUTING_TABLE_SPEC
from services.app_config import CACHE_TTL_SPEC, MIN_CACHE_TTL_SECONDS, AppConfigService
from services.styling_router import RoutingContext, resolve_route

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

REST_URL = f"{SUPABASE_URL}/rest/v1"

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def admin_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def patch_row(client: httpx.Client, key: str, value: dict) -> httpx.Response:
    return client.patch(
        f"{REST_URL}/app_config",
        headers=admin_headers(),
        params={"key": f"eq.{key}"},
        json={"value": value},
    )


def get_row(client: httpx.Client, key: str) -> dict:
    r = client.get(
        f"{REST_URL}/app_config",
        headers=admin_headers(),
        params={"key": f"eq.{key}", "select": "key,value"},
    )
    r.raise_for_status()
    rows = r.json()
    assert len(rows) == 1, f"expected exactly one row for key={key!r}, got {rows}"
    return dict(rows[0]["value"])


async def live_reload_check() -> None:
    # Pin config_cache_ttl_seconds to the numeric floor for the SAME reason
    # ss026_verify_config_live_reload.py does -- proves both ACs at once
    # (any key live-reloads, AND the TTL key governing that reload is
    # itself live-reloadable) rather than working around the mechanism.
    ttl = MIN_CACHE_TTL_SECONDS
    key = AI_STYLING_ROUTING_TABLE_SPEC.key

    with httpx.Client(timeout=30) as client:
        patch_row(client, CACHE_TTL_SPEC.key, {"seconds": ttl})
        original_table_value = get_row(client, key)
        try:
            service = AppConfigService(SupabaseAppConfigRepository(), initial_ttl_seconds=ttl)

            first_snapshot = await service.snapshot()
            first_table = service.read(first_snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
            first_decision = resolve_route(first_table, RoutingContext(user_id="ss028-verify"))
            check(
                "1a. initial decision routes the seeded DEFAULT route (gemini/everyday)",
                first_decision.provider == "gemini" and first_decision.cost_class == "everyday",
                str(first_decision),
            )

            # Flip the DEFAULT route's provider/cost_class -- the smallest
            # change that is unambiguously observable in resolve_route()'s
            # output, mirroring "changing the table changes routing".
            flipped_value = dict(original_table_value)
            flipped_default = dict(flipped_value["default"])
            flipped_default["provider"] = "claude"
            flipped_default["cost_class"] = "high_stakes"
            flipped_default["reason"] = "ss028_verify_live_flip"
            flipped_value["default"] = flipped_default
            patch_row(client, key, flipped_value)

            immediate_snapshot = await service.snapshot()
            immediate_table = service.read(immediate_snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
            immediate_decision = resolve_route(
                immediate_table, RoutingContext(user_id="ss028-verify")
            )
            check(
                "1b. immediate re-read still returns the CACHED (pre-flip) decision",
                immediate_decision.provider == "gemini",
                str(immediate_decision),
            )

            await asyncio.sleep(ttl + 0.5)  # past the TTL

            after_ttl_snapshot = await service.snapshot()
            after_ttl_table = service.read(after_ttl_snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
            after_ttl_decision = resolve_route(
                after_ttl_table, RoutingContext(user_id="ss028-verify")
            )
            check(
                "1c. post-TTL re-read returns the FLIPPED decision (claude/high_stakes), same process, no restart",
                after_ttl_decision.provider == "claude"
                and after_ttl_decision.cost_class == "high_stakes"
                and after_ttl_decision.reason == "ss028_verify_live_flip",
                str(after_ttl_decision),
            )

            # Restore the seed so the row stays truthful for the next run.
            patch_row(client, key, original_table_value)
            await asyncio.sleep(ttl + 0.5)

            restored_snapshot = await service.snapshot()
            restored_table = service.read(restored_snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
            restored_decision = resolve_route(
                restored_table, RoutingContext(user_id="ss028-verify")
            )
            check(
                "1d. restored row reads back as the original default_everyday route",
                restored_decision.reason == "default_everyday",
                str(restored_decision),
            )

            # --- Check 2: malformed-row live check (SS-026's inherited
            # guarantee, re-asserted at this ticket's boundary -- N4/T4).
            patch_row(client, key, {"not": "a valid routing table"})
            await asyncio.sleep(ttl + 0.5)

            malformed_snapshot = await service.snapshot()
            malformed_table = service.read(malformed_snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
            malformed_decision = resolve_route(
                malformed_table, RoutingContext(user_id="ss028-verify")
            )
            check(
                "2a. malformed table degrades to the coded default route, not an exception",
                malformed_decision.reason == "default_everyday",
                str(malformed_decision),
            )

            other_key_read = service.read(malformed_snapshot, CACHE_TTL_SPEC)
            check(
                "2b. the OTHER seeded key (config_cache_ttl_seconds) still reads correctly in the same snapshot",
                other_key_read.seconds == ttl,
                str(other_key_read),
            )

            patch_row(client, key, original_table_value)
        finally:
            patch_row(client, CACHE_TTL_SPEC.key, {"seconds": 60})
            patch_row(client, key, original_table_value)


def main() -> int:
    asyncio.run(live_reload_check())

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
