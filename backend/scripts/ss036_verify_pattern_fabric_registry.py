"""SS-036 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise the checks in
docs/tickets/SS-036-design.md's §6.3 "backend/scripts/
ss036_verify_pattern_fabric_registry.py + manual QA" (no live-DB test
harness exists in this repo, BL-005, so this can't be a pytest test). Same
shape as backend/scripts/ss035_verify_wear_occasion.py: creates and tears
down its own throwaway user, and never leaves rows behind that would make a
re-run misleading.

Covers design §6.3's script item directly: against the linked project,
using the service-role connection, creates a throwaway user + wardrobe
item, writes fabric='Handloom Jamdani' and pattern='Block-Print' through a
REAL insert (the `wardrobe_items_normalize_pattern_fabric_trigger` fires on
this exact write path, same as SS-012's tagging write), prints the stored
(normalised) values and the resulting attribute_unknown_tags row, then
tears down everything it created -- including the attribute_unknown_tags
capture row, which has NO FK to users (deliberately, design §3.1) so it
would otherwise survive the throwaway user's deletion and pollute a re-run.

This prints for an operator to read; it does not silently exit 0 on
failure -- see main()'s return code.

Explicitly OUT OF SCOPE for this script (see design §6.3 manual QA items,
and docs/worklog/SS-036.md for what the Developer phase already verified
directly via `supabase db query --linked` in lieu of a raw
SUPABASE_DB_URL/psycopg2 connection, BL-005):
  - item 1 (RLS both directions): already verified live via `supabase db
    query --linked` with `SET ROLE authenticated` / `SET request.jwt.claims`
    for SELECT-succeeds and INSERT-denied on all five tables -- see the
    worklog. Not repeated here since it needs role-switching, not a REST
    write path.
  - item 2 (SS-012 end-to-end via a real photo through POST /wardrobe/tag):
    needs a running backend + a real Gemini call + a real device/simulator
    upload -- explicitly deferred to QA, per design §6.3.
  - item 3 (mobile EditItemTagsForm round-trip, "Raw Silk" -> "silk" on
    refetch, and whether React Query's cached value flickers before
    settling): needs actual mobile UI interaction -- deferred to QA.
  - item 4 (drift check / before-after fixture): recorded directly in
    docs/worklog/SS-036.md by the Developer phase, not by this script.

Usage: `python -m scripts.ss036_verify_pattern_fabric_registry` (from
backend/, with the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/
SUPABASE_ANON_KEY set, e.g. via `set -a && source ../.env && set +a`).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

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
    # VERIFIED THIS SESSION (SS-036 Developer phase, running this script
    # live for the first time -- every sibling verify script's docstring
    # says "NOT RUN THIS SESSION", so this gap was never previously hit):
    # deleting the AUTH user does NOT cascade to public.users. 001_initial's
    # `users` table has no FK to auth.users -- it is populated by an
    # INSERT-only trigger (002_onboarding_completed.sql's
    # on_auth_user_created), and no matching DELETE-side trigger/cascade
    # exists. Without the explicit delete below, the public.users row (and
    # anything ON DELETE CASCADE off it, e.g. wardrobe_items) is orphaned on
    # every run -- confirmed by a real orphaned row left in the live project
    # by this exact script before this fix; see docs/worklog/SS-036.md and
    # BL-131. attribute_unknown_tags is separately NOT cascaded either way
    # (no FK at all, deliberately -- design §3.1) and is cleaned up
    # independently in teardown() below.
    client.delete(f"{AUTH_URL}/admin/users/{user_id}", headers=admin_headers())
    client.delete(f"{REST_URL}/users", headers=admin_headers(), params={"id": f"eq.{user_id}"})


def pattern_fabric_normalisation(client: httpx.Client, owner_id: str) -> tuple[str, str]:
    """The script's one scenario (design §6.3): a real INSERT through the
    same write path SS-012's tagging result and the mobile edit/upload-review
    saves use -- fires wardrobe_items_normalize_pattern_fabric_trigger for
    real, not simulated. Returns (item_id, unknown_fabric_slug) for teardown.
    """
    unknown_fabric_slug = "handloom_jamdani"
    resp = client.post(
        f"{REST_URL}/wardrobe_items",
        headers=admin_headers(),
        json={
            "user_id": owner_id,
            "image_url": f"https://example.com/{uuid.uuid4()}.jpg",
            "category": "western_top",
            "pattern": "Block-Print",
            "fabric": "Handloom Jamdani",
        },
    )
    check("1. wardrobe_items insert with pattern/fabric succeeded", resp.status_code == 201, resp.text)
    row = resp.json()[0] if resp.status_code == 201 else {}
    item_id = str(row.get("id", ""))

    stored_pattern = row.get("pattern")
    stored_fabric = row.get("fabric")
    print(f"    stored pattern = {stored_pattern!r}, stored fabric = {stored_fabric!r}")
    check("2. 'Block-Print' normalised to canonical 'block_print'", stored_pattern == "block_print", str(stored_pattern))
    check(
        "3. 'Handloom Jamdani' normalised (kept, not dropped) to 'handloom_jamdani'",
        stored_fabric == unknown_fabric_slug,
        str(stored_fabric),
    )

    r = client.get(
        f"{REST_URL}/attribute_unknown_tags",
        headers=admin_headers(),
        params={
            "attribute": "eq.fabric",
            "slug": f"eq.{unknown_fabric_slug}",
            "select": "attribute,slug,occurrences,sample_source,sample_user_id",
        },
    )
    capture_rows = r.json() if r.status_code == 200 else []
    print(f"    attribute_unknown_tags rows = {capture_rows}")
    check(
        "4. unknown fabric captured exactly once with sample_source='wardrobe_items'",
        len(capture_rows) == 1
        and capture_rows[0]["occurrences"] == 1
        and capture_rows[0]["sample_source"] == "wardrobe_items"
        and capture_rows[0]["sample_user_id"] == owner_id,
        str(capture_rows),
    )

    r_patterns = client.get(
        f"{REST_URL}/attribute_unknown_tags",
        headers=admin_headers(),
        params={"attribute": "eq.pattern", "slug": "eq.block_print", "select": "slug"},
    )
    check(
        "5. a KNOWN pattern ('block_print') is never captured as unknown",
        r_patterns.status_code == 200 and r_patterns.json() == [],
        r_patterns.text,
    )

    return item_id, unknown_fabric_slug


def teardown(client: httpx.Client, owner_id: str, unknown_fabric_slug: str) -> None:
    delete_user(client, owner_id)
    # attribute_unknown_tags has NO FK to users (design §3.1, deliberate --
    # a deleted user must not break capture) so it survives the user
    # delete above and must be cleaned up explicitly, or a re-run of this
    # script would see occurrences=2 and misreport a false failure.
    r = client.delete(
        f"{REST_URL}/attribute_unknown_tags",
        headers=admin_headers(),
        params={"attribute": "eq.fabric", "slug": f"eq.{unknown_fabric_slug}"},
    )
    check("6. teardown: probe capture row removed", r.status_code in (200, 204), r.text)


async def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    owner_email = f"ss036-owner-{run_id}@example.com"
    password = "SS036-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        owner_id = create_user(client, owner_email, password)
        unknown_fabric_slug = "handloom_jamdani"
        try:
            _item_id, unknown_fabric_slug = pattern_fabric_normalisation(client, owner_id)
        finally:
            teardown(client, owner_id, unknown_fabric_slug)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    print(
        "REMINDER: this script does not cover design §6.3 manual QA items 1 (RLS both "
        "directions -- already verified via `supabase db query --linked`, see the worklog), "
        "2 (real SS-012 /wardrobe/tag path against a real photo), or 3 (mobile "
        "EditItemTagsForm round-trip) -- run those separately per "
        "docs/tickets/SS-036-design.md §6.3."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
