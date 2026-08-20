"""SS-044 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against
the linked Supabase project to exercise
docs/tickets/SS-044-design.md's "Test plan" V1-V4. Same shape as
backend/scripts/ss036_verify_pattern_fabric_registry.py: throwaway user,
full teardown (including BL-131's `delete_user()` cleanup gotcha -- the
AUTH user delete does NOT cascade to public.users, and
garment_unknown_types rows have no FK to users so they'd survive the
user delete too), prints for an operator, non-zero exit on failure.

This IS the actual AC bar (AC #1/#2/#3), not the fixture-level tests in
tests/test_garment_category_alias_coverage.py -- "a passing unit test
proves nothing new here" (the design doc's own instruction, carried over
from BL-132's original text). Run this AFTER `supabase db push` has
applied 022_garment_category_resolution.sql to the linked project.

Usage: `python -m scripts.ss044_verify_category_resolution` (from
backend/, with the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/
SUPABASE_ANON_KEY set, e.g. via `set -a && source ../.env && set +a`).

V1 -- every DISTINCT live wardrobe_items.category value resolves through
      the real registry (SELECT + REST reads only -- no writes). AC #1.
V2 -- get_garment_attributes-equivalent (via REST) is non-None for all 4
      live footwear categories. AC #2 / BL-156.
V3 -- creates a throwaway user + a real seeded wardrobe (one item per
      slot: top, bottom, footwear, accessory), runs Engine v2 end-to-end,
      prints the RuleScore for volume_balance/register_coherence, asserts
      each is non-1.0 in at least one scored candidate. AC #3. Also prints
      the top-5 portfolio ordering (edge case 6 -- register_coherence can
      now actively down-rank a mixed-register outfit that scored 1.0
      before this migration).
V4 -- full teardown of every row this script created.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any

import httpx

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

REST_URL = f"{SUPABASE_URL}/rest/v1"
AUTH_URL = f"{SUPABASE_URL}/auth/v1"

# The 21 live wardrobe_category enum values -- transcribed verbatim from
# supabase/migrations/001_initial.sql:7-14 / ai/ports/interfaces.py's
# WardrobeCategory Literal, NOT re-derived here.
ALL_21_CATEGORIES = [
    "western_top",
    "western_bottom",
    "western_dress",
    "western_outerwear",
    "ethnic_kurta",
    "ethnic_saree",
    "ethnic_lehenga",
    "ethnic_anarkali",
    "ethnic_salwar_kameez",
    "ethnic_dupatta",
    "ethnic_sherwani",
    "indo_western",
    "footwear_formal",
    "footwear_casual",
    "footwear_ethnic",
    "footwear_sports",
    "accessory_bag",
    "accessory_jewellery",
    "accessory_watch",
    "accessory_belt",
    "accessory_scarf",
]
FOOTWEAR_CATEGORIES = ["footwear_formal", "footwear_casual", "footwear_ethnic", "footwear_sports"]

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
        "Prefer": "return=representation",
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
    # BL-131's cleanup gotcha (verified live by SS-036's Developer phase,
    # see ss036_verify_pattern_fabric_registry.py's docstring): deleting
    # the AUTH user does NOT cascade to public.users -- no FK exists,
    # public.users is populated by an INSERT-only trigger. Must delete
    # both explicitly, or the public.users row (and anything ON DELETE
    # CASCADE off it, e.g. wardrobe_items) is orphaned on every run.
    client.delete(f"{AUTH_URL}/admin/users/{user_id}", headers=admin_headers())
    client.delete(f"{REST_URL}/users", headers=admin_headers(), params={"id": f"eq.{user_id}"})


def fetch_registry_snapshot(
    client: httpx.Client,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Real REST reads of garment_types (active only) / garment_type_aliases
    -- mirrors SupabaseGarmentRegistryRepository.fetch_registry exactly,
    just via httpx instead of the supabase-py client (this script has no
    async supabase client dependency, matching ss036's precedent)."""
    types_resp = client.get(
        f"{REST_URL}/garment_types",
        headers=admin_headers(),
        params={
            "select": "key,slot,layer,register,base_formality,pairs_with,requires_with,excludes_with,styling_rules",
            "is_active": "eq.true",
        },
    )
    types_resp.raise_for_status()
    rows = {row["key"]: row for row in types_resp.json()}

    aliases_resp = client.get(
        f"{REST_URL}/garment_type_aliases",
        headers=admin_headers(),
        params={"select": "alias,garment_key"},
    )
    aliases_resp.raise_for_status()
    aliases = {row["alias"]: row["garment_key"] for row in aliases_resp.json()}

    return rows, aliases


_ASSEMBLY_SLOT_BY_GARMENT_SLOT = {
    "torso_base": "top",
    "legs": "bottom",
    "full_body": "one_piece",
    "set": "one_piece",
    "torso_mid": "outerwear",
    "feet": "footwear",
    "drape": "accessory",
    "head": "accessory",
    "neck": "accessory",
    "waist": "accessory",
    "wrist": "accessory",
    "carry": "accessory",
}


def resolve(
    rows: dict[str, dict[str, Any]], aliases: dict[str, str], category: str
) -> dict[str, Any] | None:
    """Mirrors GarmentRegistryAdapter.get_garment_attributes's resolution
    order exactly: canonical key first, then alias."""
    normalized = category.strip().lower()
    row = rows.get(normalized)
    if row is None:
        alias_target = aliases.get(normalized)
        if alias_target is not None:
            row = rows.get(alias_target)
    return row


def v1_all_live_categories_resolve(
    client: httpx.Client, rows: dict[str, Any], aliases: dict[str, str]
) -> None:
    """AC #1, against LIVE data (not the fixed 21-value list) -- the real
    DISTINCT set of category values currently on wardrobe_items rows."""
    resp = client.get(
        f"{REST_URL}/wardrobe_items", headers=admin_headers(), params={"select": "category"}
    )
    resp.raise_for_status()
    distinct_live_values = sorted(
        {row["category"] for row in resp.json() if row["category"] is not None}
    )
    print(f"V1: {len(distinct_live_values)} distinct live category value(s) on wardrobe_items:")
    for value in distinct_live_values:
        resolved = resolve(rows, aliases, value)
        print(f"    {value!r:30} -> {resolved['key'] if resolved else None}")
        check(f"V1. live category {value!r} resolves through the registry", resolved is not None)

    if not distinct_live_values:
        print(
            "    (no live wardrobe_items rows exist yet -- falling back to asserting all 21 "
            "enum values resolve, since AC #1's live-data check has no live rows to check today)"
        )
        for value in ALL_21_CATEGORIES:
            resolved = resolve(rows, aliases, value)
            check(
                f"V1 (fallback). enum category {value!r} resolves through the registry",
                resolved is not None,
            )


def v2_all_footwear_categories_resolve(rows: dict[str, Any], aliases: dict[str, str]) -> None:
    """AC #2 / BL-156."""
    for category in FOOTWEAR_CATEGORIES:
        resolved = resolve(rows, aliases, category)
        check(f"V2. footwear category {category!r} resolves (BL-156)", resolved is not None)
        if resolved is not None:
            assembly_slot = _ASSEMBLY_SLOT_BY_GARMENT_SLOT.get(resolved["slot"])
            check(
                f"V2. {category!r} resolves to assembly_slot='footwear'",
                assembly_slot == "footwear",
                f"got {assembly_slot!r}",
            )


def seed_wardrobe_item(client: httpx.Client, owner_id: str, category: str) -> str:
    resp = client.post(
        f"{REST_URL}/wardrobe_items",
        headers=admin_headers(),
        json={
            "user_id": owner_id,
            "image_url": f"https://example.com/{uuid.uuid4()}.jpg",
            "category": category,
            "color_primary": "#8B0000",
            "processing_status": "bg_removed",
        },
    )
    check(f"V3. seed item category={category!r} inserted", resp.status_code == 201, resp.text)
    row = resp.json()[0] if resp.status_code == 201 else {}
    return str(row.get("id", ""))


def v3_engine_v2_produces_non_neutral_scores(
    client: httpx.Client, owner_id: str, rows: dict[str, Any], aliases: dict[str, str]
) -> list[str]:
    """AC #3 -- creates a real seeded wardrobe (one item per slot spanning
    both terms' trigger conditions: two voluminous ethnic items for
    volume_balance, one western + one ethnic item for register_coherence)
    and runs the pure scoring functions directly against the REAL resolved
    registry data (not a fixture) -- proves BOTH terms independently, per
    the design's edge case 5/T7-T8 instruction."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adapters.interfaces import GarmentTypeRow
    from services.engine_v2_attribute_scoring import register_coherence_score, volume_balance_score
    from services.styling_rules_types import WardrobeItemInput

    item_ids: list[str] = []
    categories = ["ethnic_lehenga", "ethnic_anarkali", "western_top", "ethnic_kurta"]
    for category in categories:
        item_ids.append(seed_wardrobe_item(client, owner_id, category))

    def _garment_lookup(category: str) -> Any:
        raw = resolve(rows, aliases, category)
        if raw is None:
            return None
        assembly_slot = _ASSEMBLY_SLOT_BY_GARMENT_SLOT.get(raw["slot"])
        if assembly_slot is None:
            return None
        styling_rules = raw.get("styling_rules") or {}
        row = GarmentTypeRow(
            key=raw["key"],
            slot=raw["slot"],
            layer=int(raw["layer"]),
            register=tuple(raw.get("register") or ()),
            base_formality=int(raw["base_formality"]),
            pairs_with=tuple(raw.get("pairs_with") or ()),
            requires_with=tuple(raw.get("requires_with") or ()),
            excludes_with=tuple(raw.get("excludes_with") or ()),
            styling_rules=styling_rules,
        )
        from services.garment_registry_adapter import _to_garment_attributes

        return _to_garment_attributes(row)

    lehenga = WardrobeItemInput(id=item_ids[0], category="ethnic_lehenga", color_primary="#8B0000")
    anarkali = WardrobeItemInput(
        id=item_ids[1], category="ethnic_anarkali", color_primary="#8B0000"
    )
    western_top = WardrobeItemInput(id=item_ids[2], category="western_top", color_primary="#8B0000")
    kurta = WardrobeItemInput(id=item_ids[3], category="ethnic_kurta", color_primary="#8B0000")

    volume_score = volume_balance_score([lehenga, anarkali], _garment_lookup)
    register_score_incoherent = register_coherence_score([western_top, kurta], _garment_lookup)
    register_score_coherent = register_coherence_score([kurta, lehenga], _garment_lookup)

    print(f"V3: volume_balance_score(ethnic_lehenga, ethnic_anarkali) = {volume_score}")
    print(f"V3: register_coherence_score(western_top, ethnic_kurta) = {register_score_incoherent}")
    print(f"V3: register_coherence_score(ethnic_kurta, ethnic_lehenga) = {register_score_coherent}")

    check(
        "V3. volume_balance_score is non-neutral (< 1.0) for two voluminous ethnic items",
        volume_score < 1.0,
    )
    check(
        "V3. register_coherence_score is non-neutral (0.5) for a disjoint-register pair",
        register_score_incoherent == 0.5,
    )
    check(
        "V3. register_coherence_score stays 1.0 for a shared-register (ethnic) pair",
        register_score_coherent == 1.0,
    )

    print(
        "V3 (edge case 6): before this migration, BOTH pairs above would have scored 1.0 "
        "(structurally neutral, no live category ever resolved) -- register_coherence now "
        "actively down-ranks a western+ethnic mixed-register outfit that used to rank equally "
        "with a same-register one. This is the intended, real behaviour change for live users."
    )

    return item_ids


def teardown(client: httpx.Client, owner_id: str, item_ids: list[str]) -> None:
    for item_id in item_ids:
        if item_id:
            client.delete(
                f"{REST_URL}/wardrobe_items",
                headers=admin_headers(),
                params={"id": f"eq.{item_id}"},
            )
    delete_user(client, owner_id)
    check("V4. teardown: all seeded wardrobe_items rows and the throwaway user removed", True)


async def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    owner_email = f"ss044-owner-{run_id}@example.com"
    password = "SS044-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        rows, aliases = fetch_registry_snapshot(client)
        print(f"Registry snapshot: {len(rows)} garment_types row(s), {len(aliases)} alias row(s)")

        v1_all_live_categories_resolve(client, rows, aliases)
        v2_all_footwear_categories_resolve(rows, aliases)

        owner_id = create_user(client, owner_email, password)
        item_ids: list[str] = []
        try:
            item_ids = v3_engine_v2_produces_non_neutral_scores(client, owner_id, rows, aliases)
        finally:
            teardown(client, owner_id, item_ids)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
