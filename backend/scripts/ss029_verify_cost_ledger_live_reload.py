"""SS-029 manual DB/live verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise the checks in
docs/tickets/SS-029-design.md's §6.8 "Manual / live verification" (no
live-DB test harness exists in this repo, BL-005, so this can't be a pytest
test). Same shape as backend/scripts/ss026_verify_config_live_reload.py:
creates and tears down its own throwaway user, restores any config row it
mutates, and deletes every row/object it wrote.

Usage: `python -m scripts.ss029_verify_cost_ledger_live_reload` (from
backend/, with the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/
SUPABASE_ANON_KEY/CLOUDFLARE_R2_*/UPSTASH_REDIS_REST_*/GEMINI_API_KEY set,
e.g. via `set -a && source ../.env && set +a`).

**Migration numbering note:** the design named the schema migration
`011_ai_cost_ledger.sql`; it shipped as `012_ai_cost_ledger.sql` because the
shared live project already had a real `011_*` migration applied from
SS-027 by the time this ticket's Developer phase ran `supabase db push`
(see the migration file's own header and docs/worklog/SS-029.md). The DDL
itself was applied directly via `supabase db query --linked -f
supabase/migrations/012_ai_cost_ledger.sql` rather than `db push`, since
`db push`/`db pull` both refused over the local/remote migration-history
mismatch and repairing that history is a cross-ticket operation this phase
does not have standing to perform unilaterally.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from typing import Any

import httpx
from PIL import Image

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


def anon_headers() -> dict[str, str]:
    return {"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}"}


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


def upsert_config_row(client: httpx.Client, key: str, value: dict[str, Any]) -> None:
    resp = client.post(
        f"{REST_URL}/app_config",
        headers={**admin_headers(), "Prefer": "resolution=merge-duplicates"},
        json={"key": key, "value": value, "description": f"SS-029 verification seed for {key}"},
    )
    resp.raise_for_status()


def patch_config_row(client: httpx.Client, key: str, value: dict[str, Any]) -> httpx.Response:
    return client.patch(
        f"{REST_URL}/app_config", headers=admin_headers(), params={"key": f"eq.{key}"}, json={"value": value}
    )


def rls_checks(client: httpx.Client) -> None:
    r = client.get(
        f"{REST_URL}/ai_cost_ledger", headers=anon_headers(), params={"select": "id", "limit": "1"}
    )
    check(
        "1a. anon SELECT on ai_cost_ledger returns 200 with zero rows, not an error",
        r.status_code == 200 and r.json() == [],
        r.text,
    )

    r2 = client.post(
        f"{REST_URL}/ai_cost_ledger",
        headers={**anon_headers(), "Content-Type": "application/json"},
        json={
            "user_id": str(uuid.uuid4()),
            "request_id": str(uuid.uuid4()),
            "provider": "gemini",
            "model": "probe",
            "feature": "wardrobe_tagging",
        },
    )
    check(
        "1b. anon INSERT on ai_cost_ledger is rejected by RLS (401/403, code 42501)",
        r2.status_code in (401, 403),
        r2.text,
    )

    r3 = client.get(
        f"{REST_URL}/ai_cost_ledger", headers=admin_headers(), params={"select": "id", "limit": "1"}
    )
    check("1c. service_role SELECT on ai_cost_ledger succeeds", r3.status_code == 200, r3.text)

    r4 = client.get(f"{REST_URL}/ai_cost_breakdown", headers=admin_headers(), params={"limit": "1"})
    check("1d. ai_cost_breakdown view is queryable by service_role", r4.status_code == 200, r4.text)


def config_seed_and_live_reload_check(client: httpx.Client) -> None:
    from services.app_config import CACHE_TTL_SPEC, MIN_CACHE_TTL_SECONDS, AppConfigService
    from services.cost_config_specs import _DEFAULT_PRICE_TABLE, AI_COST_BUDGETS_SPEC

    upsert_config_row(client, "ai_price_table", _DEFAULT_PRICE_TABLE.model_dump(mode="json"))
    upsert_config_row(
        client,
        "ai_cost_budgets",
        {
            "free": {"daily_paise": 500, "monthly_paise": 2500, "enforce": True, "fail_open": False},
            "premium": {"daily_paise": 5000, "monthly_paise": 50000, "enforce": True, "fail_open": True},
            "premium_annual": {
                "daily_paise": 5000,
                "monthly_paise": 50000,
                "enforce": True,
                "fail_open": True,
            },
        },
    )
    check("2a. ai_price_table and ai_cost_budgets rows seeded", True)

    ttl = MIN_CACHE_TTL_SECONDS
    patch_config_row(client, CACHE_TTL_SPEC.key, {"seconds": ttl})
    try:
        from adapters.app_config_repository import SupabaseAppConfigRepository

        service = AppConfigService(SupabaseAppConfigRepository(), initial_ttl_seconds=ttl)

        async def _live_reload() -> None:
            first = await service.snapshot()
            first_read = service.read(first, AI_COST_BUDGETS_SPEC)
            check(
                "2b. initial read reflects the seeded free daily ceiling (500 paise)",
                first_read.free.daily_paise == 500,
                str(first_read),
            )

            patch_config_row(client, "ai_cost_budgets", {"free": {"daily_paise": 999, "monthly_paise": 2500, "enforce": True, "fail_open": False}, "premium": {"daily_paise": 5000, "monthly_paise": 50000, "enforce": True, "fail_open": True}, "premium_annual": {"daily_paise": 5000, "monthly_paise": 50000, "enforce": True, "fail_open": True}})

            immediate = await service.snapshot()
            immediate_read = service.read(immediate, AI_COST_BUDGETS_SPEC)
            check(
                "2c. immediate re-read still cached (500), proves the cache is not a live-read",
                immediate_read.free.daily_paise == 500,
                str(immediate_read),
            )

            await asyncio.sleep(ttl + 0.5)

            after_ttl = await service.snapshot()
            after_ttl_read = service.read(after_ttl, AI_COST_BUDGETS_SPEC)
            check(
                "2d. post-TTL re-read returns the new value (999), same process, no redeploy/restart",
                after_ttl_read.free.daily_paise == 999,
                str(after_ttl_read),
            )

        asyncio.run(_live_reload())
    finally:
        # Restore the free ceiling back to the real operative value and the
        # cache TTL back to its migration seed.
        patch_config_row(
            client,
            "ai_cost_budgets",
            {
                "free": {"daily_paise": 500, "monthly_paise": 2500, "enforce": True, "fail_open": False},
                "premium": {"daily_paise": 5000, "monthly_paise": 50000, "enforce": True, "fail_open": True},
                "premium_annual": {
                    "daily_paise": 5000,
                    "monthly_paise": 50000,
                    "enforce": True,
                    "fail_open": True,
                },
            },
        )
        patch_config_row(client, CACHE_TTL_SPEC.key, {"seconds": 60})


def _synthetic_jpeg() -> bytes:
    image = Image.new("RGB", (64, 64), (30, 60, 90))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def _fetch_ledger_rows_sync(client: httpx.Client, request_id: str) -> list[dict[str, Any]]:
    """Plain sync helper (not called directly from an `async def` body) so
    this blocking httpx call doesn't trip ASYNC212 -- mirrors
    ss026_verify_config_live_reload.py's own `patch_row` pattern."""
    r = client.get(
        f"{REST_URL}/ai_cost_ledger",
        headers=admin_headers(),
        params={"select": "*", "request_id": f"eq.{request_id}"},
    )
    return list(r.json())


def _cleanup_verification_rows_sync(client: httpx.Client, request_id: str, item_id: str) -> None:
    client.delete(
        f"{REST_URL}/ai_cost_ledger", headers=admin_headers(), params={"request_id": f"eq.{request_id}"}
    )
    client.delete(f"{REST_URL}/wardrobe_items", headers=admin_headers(), params={"id": f"eq.{item_id}"})


async def _drive_real_tag_call(client: httpx.Client, jwt: str, user_id: str) -> None:
    from adapters.app_config_repository import SupabaseAppConfigRepository
    from adapters.r2_storage import R2StorageClient
    from adapters.supabase_cost_ledger import SupabaseCostLedger
    from adapters.upstash_rate_limiter import UpstashRateLimiter
    from adapters.wardrobe_repository import SupabaseWardrobeRepository
    from ai.adapters.gemini_vision_adapter import MODEL as GEMINI_MODEL
    from ai.adapters.gemini_vision_adapter import GeminiVisionAdapter
    from services.app_config import AppConfigService
    from services.cost_budget_gate import CostBudgetGate
    from services.cost_config_specs import AI_PRICE_TABLE_SPEC
    from services.gemini_rate_limiter import GeminiRateLimiter
    from services.ist_window import ist_today
    from services.price_table import PriceTable
    from services.tag_cache import TagCache
    from services.wardrobe_tagging_service import (
        PROVIDER,
        WardrobeTaggingService,
        original_image_key,
    )

    item_id = str(uuid.uuid4())
    repository = SupabaseWardrobeRepository()

    await repository.upsert_uploaded_row(
        jwt=jwt, item_id=item_id, user_id=user_id, image_key=original_image_key(user_id, item_id)
    )

    storage = R2StorageClient()
    image_bytes = _synthetic_jpeg()
    storage.put_object_bytes(original_image_key(user_id, item_id), image_bytes, "image/jpeg")

    app_config_service = AppConfigService(SupabaseAppConfigRepository())
    snapshot = await app_config_service.snapshot()
    price_table = PriceTable(app_config_service.read(snapshot, AI_PRICE_TABLE_SPEC))
    estimate = price_table.estimate(provider=PROVIDER, model=GEMINI_MODEL, at=ist_today())

    limiter = UpstashRateLimiter()
    gate = CostBudgetGate(limiter, app_config_service)
    request_id = str(uuid.uuid4())
    decision = await gate.reserve(
        user_id=user_id,
        tier="free",
        estimate_micropaise=estimate.cost_micropaise,
        config_snapshot=snapshot,
    )
    check("3a. real budget-gate reservation is allowed for a fresh throwaway user", decision.allowed)
    if not decision.allowed or decision.reservation is None:
        return

    occasion_normalizer = _occasion_normalizer()
    cost_ledger = SupabaseCostLedger()
    service = WardrobeTaggingService(
        GeminiVisionAdapter(occasion_normalizer=occasion_normalizer, registry_jwt=jwt),
        repository,
        storage,
        TagCache(),
        GeminiRateLimiter(),
        occasion_normalizer,
        gate,
        cost_ledger,
    )

    await service.tag(
        jwt=jwt,
        user_id=user_id,
        item_id=item_id,
        request_id=request_id,
        reservation=decision.reservation,
        price_table=price_table,
    )

    rows = _fetch_ledger_rows_sync(client, request_id)
    check(
        "3b. exactly one ai_cost_ledger row written for this real /tag call",
        len(rows) == 1,
        str(rows),
    )
    if rows:
        row = rows[0]
        check(
            "3c. cost_paise is populated (non-null) on the real row",
            row.get("cost_paise") is not None,
            str(row),
        )
        check(
            "3d. unit_price_snapshot is populated (non-empty) on the real row",
            bool(row.get("unit_price_snapshot")),
            str(row),
        )
        print(f"    real ai_cost_ledger row: cost_paise={row.get('cost_paise')} "
              f"pricing_status={row.get('pricing_status')} model={row.get('model')} "
              f"tokens_in={row.get('tokens_in')} tokens_out={row.get('tokens_out')}")

    # Cleanup: this script's own rows only.
    _cleanup_verification_rows_sync(client, request_id, item_id)


def _occasion_normalizer() -> Any:
    from adapters.occasion_repository import SupabaseOccasionRepository
    from services.occasion_normalizer import OccasionNormalizer

    return OccasionNormalizer(SupabaseOccasionRepository())


def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    email = f"ss029-verify-{run_id}@example.com"
    password = "SS029-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        rls_checks(client)
        config_seed_and_live_reload_check(client)

        user_id = create_user(client, email, password)
        jwt = sign_in(client, email, password)
        try:
            asyncio.run(_drive_real_tag_call(client, jwt, user_id))
        finally:
            delete_user(client, user_id)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
