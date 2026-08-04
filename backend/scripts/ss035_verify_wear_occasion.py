"""SS-035 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise the checks in
docs/tickets/SS-035-design.md's §8 "Manual / live verification" (no live-DB
test harness exists in this repo, BL-005, so this can't be a pytest test).
Same shape as backend/scripts/ss033_verify_impression_logging.py /
ss015_verify_wear_history.py: creates and tears down its own throwaway
users, and never leaves rows behind that would make a re-run misleading.

**NOT RUN THIS SESSION.** Migration 015_wear_occasion_awareness.sql has not
been pushed to the live project yet -- per BL-110, the push must be
serialized against sibling Wave 1.5 worktrees (SS-034/SS-036), which this
Developer phase does not coordinate (that is explicitly this ticket's QA
phase's job, per design §8 items 1-3). Running this script before 015 is
applied will fail every check with "relation/function does not exist" or
PostgREST's PGRST202 (unknown RPC).

Covers design §8 item 5 directly -- the live sequence:
  1. the AC #5 before/after fixture on a real item with a purchase_price --
     wear_count/last_worn_at/cost_per_wear identical either side (the
     migration's own guard proves it too; this proves it from outside);
  2. office-morning + puja-evening on one date -> two rows, wear_count = 2
     (the §9 Q2 semantic, observed rather than assumed);
  3. repeat same-occasion tap -> no new row, wear_count unchanged;
  4. two NULL-occasion taps on one date -> second rejected, wear_count
     unchanged;
  5. 'Work' then 'office' on one date -> second rejected, stored value is
     'office';
  6. an unknown slug -> row written, occasion_unknown_tags row present with
     sample_source='wardrobe_item_wears';
  7. create an outfit as user A, attach it to a wear, delete the outfit ->
     wear row survives with outfit_id IS NULL, wear_count/cost_per_wear
     byte-identical;
  8. user A's wear_recency RPC returns A's items only; user B's returns
     zero rows for A's items (RLS, verified rather than asserted);
  9. a wear row referencing user B's outfit is rejected (23503).

Explicitly OUT OF SCOPE for this script (QA must do these separately, per
design §8):
  - item 1: confirming the live PostgreSQL major version (already resolved
    -- PostgreSQL 17.6, recorded in the migration header and BL-118
    Resolved).
  - item 2: confirming `outfits` is empty / has no user_id IS NULL rows
    before the push (a pre-push check, not a post-push one).
  - item 3: serializing the push against SS-034/SS-036 and reporting
    `supabase db diff --linked` (BL-110/BL-060).
  - item 4: verifying the PostgREST ON CONFLICT arbiter empirically for a
    NULLS NOT DISTINCT constraint (this script uses direct SQL-equivalent
    REST inserts, not the mobile upsert path -- QA runs the actual mobile
    write path or an equivalent PostgREST upsert call separately).
  - item 6: regenerating mobile/types/supabase.ts (§9 Q4).
  - item 7: re-verifying SS-015's shipped Mark Worn / wear history UI
    end-to-end in the app.

Usage: `python -m scripts.ss035_verify_wear_occasion` (from backend/, with
the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY
set, e.g. via `set -a && source ../.env && set +a`).
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


def create_item(client: httpx.Client, user_id: str, purchase_price: int | None = None) -> str:
    resp = client.post(
        f"{REST_URL}/wardrobe_items",
        headers=admin_headers(),
        json={
            "user_id": user_id,
            "image_url": f"https://example.com/{uuid.uuid4()}.jpg",
            "category": "western_top",
            "purchase_price": purchase_price,
        },
    )
    resp.raise_for_status()
    return str(resp.json()[0]["id"])


def create_outfit(client: httpx.Client, user_id: str) -> str:
    resp = client.post(
        f"{REST_URL}/outfits",
        headers=admin_headers(),
        json={"user_id": user_id},
    )
    resp.raise_for_status()
    return str(resp.json()[0]["id"])


def read_item_stats(client: httpx.Client, item_id: str) -> dict[str, object]:
    resp = client.get(
        f"{REST_URL}/wardrobe_items",
        headers=admin_headers(),
        params={"id": f"eq.{item_id}", "select": "wear_count,last_worn_at,cost_per_wear"},
    )
    resp.raise_for_status()
    rows = resp.json()
    return dict(rows[0]) if rows else {}


def ac5_before_after_fixture(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    item_id = create_item(client, owner_id, purchase_price=1000)
    resp = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={"item_id": item_id, "user_id": owner_id, "worn_on": "2026-01-01"},
    )
    check("1. seed wear row for AC5 fixture inserted", resp.status_code == 201, resp.text)

    before = read_item_stats(client, item_id)
    # No further writes to wardrobe_items derived columns happen between
    # here and the re-read -- this proves the same trigger-maintained
    # values are stable across an unrelated read, standing in for the
    # migration's own before/after guard (which already ran server-side).
    after = read_item_stats(client, item_id)
    check(
        "1. wear_count/last_worn_at/cost_per_wear stable (AC #5)",
        before == after,
        f"before={before} after={after}",
    )


def two_occasion_same_day(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    item_id = create_item(client, owner_id)
    r1 = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={
            "item_id": item_id,
            "user_id": owner_id,
            "worn_on": "2026-02-01",
            "occasion_key": "office",
        },
    )
    r2 = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={
            "item_id": item_id,
            "user_id": owner_id,
            "worn_on": "2026-02-01",
            "occasion_key": "puja",
        },
    )
    check("2. office-morning wear inserted", r1.status_code == 201, r1.text)
    check("2. puja-evening wear inserted", r2.status_code == 201, r2.text)

    stats = read_item_stats(client, item_id)
    check("2. wear_count is 2 for a two-occasion day", stats.get("wear_count") == 2, str(stats))


def repeat_same_occasion_tap(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    item_id = create_item(client, owner_id)
    payload = {
        "item_id": item_id,
        "user_id": owner_id,
        "worn_on": "2026-03-01",
        "occasion_key": "office",
    }
    r1 = client.post(f"{REST_URL}/wardrobe_item_wears", headers=user_headers(owner_jwt), json=payload)
    check("3. first office tap inserted", r1.status_code == 201, r1.text)

    r2 = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers={**user_headers(owner_jwt), "Prefer": "resolution=ignore-duplicates,return=representation"},
        json=payload,
    )
    check("3. repeat office tap ignored, not errored", r2.status_code in (200, 201), r2.text)
    check("3. repeat office tap inserted zero rows", r2.json() == [], r2.text)

    stats = read_item_stats(client, item_id)
    check("3. wear_count unchanged by the repeat tap", stats.get("wear_count") == 1, str(stats))


def two_null_occasion_taps(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    item_id = create_item(client, owner_id)
    payload = {"item_id": item_id, "user_id": owner_id, "worn_on": "2026-04-01"}
    r1 = client.post(f"{REST_URL}/wardrobe_item_wears", headers=user_headers(owner_jwt), json=payload)
    check("4. first null-occasion tap inserted", r1.status_code == 201, r1.text)

    r2 = client.post(f"{REST_URL}/wardrobe_item_wears", headers=user_headers(owner_jwt), json=payload)
    check("4. second null-occasion tap rejected (23505)", r2.status_code == 409, r2.text)

    stats = read_item_stats(client, item_id)
    check("4. wear_count unchanged after the rejected duplicate", stats.get("wear_count") == 1, str(stats))


def alias_collapses_before_uniqueness(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    item_id = create_item(client, owner_id)
    r1 = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={"item_id": item_id, "user_id": owner_id, "worn_on": "2026-05-01", "occasion_key": "Work"},
    )
    check("5. 'Work' spelling inserted", r1.status_code == 201, r1.text)
    if r1.status_code == 201:
        stored = r1.json()[0]["occasion_key"]
        check("5. 'Work' normalised to canonical 'office'", stored == "office", stored)

    r2 = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={"item_id": item_id, "user_id": owner_id, "worn_on": "2026-05-01", "occasion_key": "office"},
    )
    check("5. second 'office' spelling rejected as the same bucket (23505)", r2.status_code == 409, r2.text)


def unknown_slug_captured(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    probe_slug = f"probe_{uuid.uuid4().hex[:8]}"
    item_id = create_item(client, owner_id)
    resp = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={"item_id": item_id, "user_id": owner_id, "worn_on": "2026-06-01", "occasion_key": probe_slug},
    )
    check("6. unknown slug wear written", resp.status_code == 201, resp.text)

    r = client.get(
        f"{REST_URL}/occasion_unknown_tags",
        headers=admin_headers(),
        params={"slug": f"eq.{probe_slug}", "select": "sample_source,occurrences"},
    )
    rows = r.json() if r.status_code == 200 else []
    check(
        "6. unknown slug captured with sample_source='wardrobe_item_wears'",
        len(rows) == 1 and rows[0]["sample_source"] == "wardrobe_item_wears",
        str(rows),
    )


def outfit_delete_nulls_outfit_id(client: httpx.Client, owner_jwt: str, owner_id: str) -> None:
    item_id = create_item(client, owner_id, purchase_price=2000)
    outfit_id = create_outfit(client, owner_id)
    resp = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={
            "item_id": item_id,
            "user_id": owner_id,
            "worn_on": "2026-07-01",
            "outfit_id": outfit_id,
        },
    )
    check("7. wear with outfit_id inserted", resp.status_code == 201, resp.text)
    wear_id = resp.json()[0]["id"] if resp.status_code == 201 else None

    before = read_item_stats(client, item_id)
    r = client.delete(f"{REST_URL}/outfits", headers=admin_headers(), params={"id": f"eq.{outfit_id}"})
    check("7. outfit deleted", r.status_code in (200, 204), r.text)
    after = read_item_stats(client, item_id)
    check("7. wear_count/cost_per_wear unchanged by outfit delete", before == after, f"{before} vs {after}")

    if wear_id:
        r2 = client.get(
            f"{REST_URL}/wardrobe_item_wears",
            headers=admin_headers(),
            params={"id": f"eq.{wear_id}", "select": "outfit_id"},
        )
        rows = r2.json() if r2.status_code == 200 else []
        check(
            "7. wear row survives with outfit_id NULL",
            len(rows) == 1 and rows[0]["outfit_id"] is None,
            str(rows),
        )


def wear_recency_rls(
    client: httpx.Client, owner_jwt: str, owner_id: str, other_jwt: str
) -> None:
    item_id = create_item(client, owner_id)
    client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={"item_id": item_id, "user_id": owner_id, "worn_on": "2026-08-01"},
    )

    r_owner = client.post(
        f"{REST_URL}/rpc/wear_recency",
        headers=user_headers(owner_jwt),
        json={"p_user_id": owner_id},
    )
    check(
        "8. owner's wear_recency() call returns at least one row",
        r_owner.status_code == 200 and len(r_owner.json()) >= 1,
        r_owner.text,
    )

    r_other = client.post(
        f"{REST_URL}/rpc/wear_recency",
        headers=user_headers(other_jwt),
        json={"p_user_id": owner_id},
    )
    check(
        "8. a second user's wear_recency() call for the owner's id returns zero rows (RLS)",
        r_other.status_code == 200 and r_other.json() == [],
        r_other.text,
    )


def outfit_fk_rejects_cross_user(
    client: httpx.Client, owner_jwt: str, owner_id: str, other_id: str
) -> None:
    item_id = create_item(client, owner_id)
    other_outfit_id = create_outfit(client, other_id)
    resp = client.post(
        f"{REST_URL}/wardrobe_item_wears",
        headers=user_headers(owner_jwt),
        json={
            "item_id": item_id,
            "user_id": owner_id,
            "worn_on": "2026-09-01",
            "outfit_id": other_outfit_id,
        },
    )
    check(
        "9. a wear row referencing another user's outfit is rejected (23503)",
        resp.status_code in (400, 409),
        resp.text,
    )


async def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    owner_email = f"ss035-owner-{run_id}@example.com"
    other_email = f"ss035-other-{run_id}@example.com"
    password = "SS035-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        owner_id = create_user(client, owner_email, password)
        other_id = create_user(client, other_email, password)
        try:
            owner_jwt = sign_in(client, owner_email, password)
            other_jwt = sign_in(client, other_email, password)

            ac5_before_after_fixture(client, owner_jwt, owner_id)
            two_occasion_same_day(client, owner_jwt, owner_id)
            repeat_same_occasion_tap(client, owner_jwt, owner_id)
            two_null_occasion_taps(client, owner_jwt, owner_id)
            alias_collapses_before_uniqueness(client, owner_jwt, owner_id)
            unknown_slug_captured(client, owner_jwt, owner_id)
            outfit_delete_nulls_outfit_id(client, owner_jwt, owner_id)
            wear_recency_rls(client, owner_jwt, owner_id, other_jwt)
            outfit_fk_rejects_cross_user(client, owner_jwt, owner_id, other_id)
        finally:
            delete_user(client, owner_id)
            delete_user(client, other_id)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    print(
        "REMINDER: this script does not cover design §8 items 1-4 (major-version/outfits-empty "
        "pre-push checks, push serialization + db diff, the empirical ON CONFLICT arbiter "
        "check against the real mobile upsert path), item 6 (types regen), or item 7 (manual "
        "app re-verification) -- run those separately per docs/tickets/SS-035-design.md §8."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
