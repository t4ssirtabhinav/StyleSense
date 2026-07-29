"""SS-026 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise the checks in
docs/tickets/SS-026-design.md's §7.4 "Manual / live verification" (no
live-DB test harness exists in this repo, BL-005, so this can't be a pytest
test). Same shape as backend/scripts/ss015_verify_wear_history.py: creates
and tears down its own throwaway user, restores any row it mutates so the
seed stays truthful for the next run.

Usage: `python -m scripts.ss026_verify_config_live_reload` (from backend/,
with the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/
SUPABASE_ANON_KEY set, e.g. via `set -a && source ../.env && set +a`).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

from adapters.app_config_repository import SupabaseAppConfigRepository
from services.app_config import CACHE_TTL_SPEC, MIN_CACHE_TTL_SECONDS, AppConfigService
from services.app_config_specs import GEMINI_QUOTA_CEILING_SPEC

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

REST_URL = f"{SUPABASE_URL}/rest/v1"
AUTH_URL = f"{SUPABASE_URL}/auth/v1"

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


def create_user(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post(
        f"{AUTH_URL}/admin/users",
        headers=admin_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    resp.raise_for_status()
    return str(resp.json()["id"])


def delete_user(client: httpx.Client, user_id: str) -> None:
    client.delete(f"{AUTH_URL}/admin/users/{user_id}", headers=admin_headers())


def sign_in(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post(
        f"{AUTH_URL}/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def user_headers(jwt: str) -> dict[str, str]:
    return {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def patch_row(
    client: httpx.Client, key: str, value: dict, headers: dict[str, str]
) -> httpx.Response:
    return client.patch(
        f"{REST_URL}/app_config",
        headers=headers,
        params={"key": f"eq.{key}"},
        json={"value": value},
    )


def sync_checks(client: httpx.Client, jwt_user: str) -> None:
    # --- Check 1: RLS, both directions.
    r = client.get(
        f"{REST_URL}/app_config",
        headers=admin_headers(),
        params={"key": f"eq.{GEMINI_QUOTA_CEILING_SPEC.key}", "select": "key,value"},
    )
    r.raise_for_status()
    check(
        "1a. service_role SELECT sees the seeded server-scoped row",
        len(r.json()) == 1 and r.json()[0]["value"] == {"rpm": 15},
        r.text,
    )

    r = client.get(
        f"{REST_URL}/app_config",
        headers=user_headers(jwt_user),
        params={"key": f"eq.{GEMINI_QUOTA_CEILING_SPEC.key}", "select": "key,value"},
    )
    check(
        "1b. authenticated SELECT of a server-scoped row returns ZERO rows, not an error",
        r.status_code == 200 and r.json() == [],
        r.text,
    )

    r = client.post(
        f"{REST_URL}/app_config",
        headers=user_headers(jwt_user),
        json={
            "key": "ss026_probe_should_never_land",
            "value": {"x": 1},
            "description": "probe row -- should be rejected by RLS",
        },
    )
    check(
        "1c. authenticated INSERT rejected by RLS (403/42501)",
        r.status_code in (401, 403),
        r.text,
    )

    r = patch_row(client, GEMINI_QUOTA_CEILING_SPEC.key, {"rpm": 999}, user_headers(jwt_user))
    check(
        "1d. authenticated UPDATE against app_config fails (RLS, no matching policy)",
        r.status_code in (401, 403) or r.json() == [],
        r.text,
    )


async def live_reload_check() -> None:
    # --- Check 2: the AC's headline demo -- no redeploy, no restart.
    #
    # AppConfigService self-referentially adopts config_cache_ttl_seconds'
    # OWN value (design §3.5) as the interval for its NEXT refresh cycle
    # after every successful fetch -- including the very first one. The
    # seed value is 60s, so `initial_ttl_seconds` below only governs the
    # window before that first successful fetch; it would otherwise be
    # silently overwritten to 60s immediately, making a short sleep never
    # observe a refetch. Pinning the seeded config_cache_ttl_seconds row to
    # MIN_CACHE_TTL_SECONDS (the numeric floor _clamp_ttl enforces -- a
    # smaller value would silently clamp back up to this same number, see
    # design §3.5) here demonstrates BOTH ACs at once (any key live-reloads,
    # AND the TTL key governing that reload is itself live-reloadable)
    # rather than working around the mechanism.
    ttl = MIN_CACHE_TTL_SECONDS
    with httpx.Client(timeout=30) as client:
        patch_row(client, CACHE_TTL_SPEC.key, {"seconds": ttl}, admin_headers())
        try:
            service = AppConfigService(SupabaseAppConfigRepository(), initial_ttl_seconds=ttl)

            first = await service.snapshot()
            first_read = service.read(first, GEMINI_QUOTA_CEILING_SPEC)
            check("2a. initial read == seeded value (15)", first_read.rpm == 15, str(first_read))

            patch_row(client, GEMINI_QUOTA_CEILING_SPEC.key, {"rpm": 999}, admin_headers())

            immediate = await service.snapshot()
            immediate_read = service.read(immediate, GEMINI_QUOTA_CEILING_SPEC)
            check(
                "2b. immediate re-read still returns cached value (15), proves the cache not a live-read",
                immediate_read.rpm == 15,
                str(immediate_read),
            )

            await asyncio.sleep(ttl + 0.5)  # past the TTL

            after_ttl = await service.snapshot()
            after_ttl_read = service.read(after_ttl, GEMINI_QUOTA_CEILING_SPEC)
            check(
                "2c. post-TTL re-read returns the new value (999), same process, no restart",
                after_ttl_read.rpm == 999,
                str(after_ttl_read),
            )

            # Restore the seed so the row stays truthful for the next run.
            patch_row(client, GEMINI_QUOTA_CEILING_SPEC.key, {"rpm": 15}, admin_headers())

            # --- Check 3: malformed-row live check.
            patch_row(
                client, GEMINI_QUOTA_CEILING_SPEC.key, {"rpm": "not-a-number"}, admin_headers()
            )
            await asyncio.sleep(ttl + 0.5)

            malformed_snapshot = await service.snapshot()
            malformed_read = service.read(malformed_snapshot, GEMINI_QUOTA_CEILING_SPEC)
            check(
                "3a. malformed value degrades to coded default (15), not an exception",
                malformed_read.rpm == 15,
                str(malformed_read),
            )

            other_key_read = service.read(malformed_snapshot, CACHE_TTL_SPEC)
            check(
                "3b. the OTHER seeded key still reads correctly in the same snapshot",
                other_key_read.seconds == ttl,
                str(other_key_read),
            )

            # Restore the seed.
            patch_row(client, GEMINI_QUOTA_CEILING_SPEC.key, {"rpm": 15}, admin_headers())
        finally:
            # Always restore config_cache_ttl_seconds to its migration seed
            # value, even if an assertion above failed.
            patch_row(client, CACHE_TTL_SPEC.key, {"seconds": 60}, admin_headers())


def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    email = f"ss026-verify-{run_id}@example.com"
    password = "SS026-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        user_id = create_user(client, email, password)
        jwt = sign_in(client, email, password)
        try:
            sync_checks(client, jwt)
        finally:
            delete_user(client, user_id)

    asyncio.run(live_reload_check())

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
