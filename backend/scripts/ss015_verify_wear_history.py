"""SS-015 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise the 7 checks in
docs/tickets/SS-015-design.md's "Test plan" section (no live-DB test harness
exists in this repo, BL-005, so this can't be a pytest test). Creates and
tears down its own throwaway users/items; safe to re-run.

Usage: `python scripts/ss015_verify_wear_history.py` (from backend/, with the
venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY set,
e.g. via `set -a && source ../.env && set +a`).
"""

from __future__ import annotations

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


def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    email_a = f"ss015-verify-a-{run_id}@example.com"
    email_b = f"ss015-verify-b-{run_id}@example.com"
    password = "SS015-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        user_a = create_user(client, email_a, password)
        user_b = create_user(client, email_b, password)
        jwt_a = sign_in(client, email_a, password)
        # jwt_b unused -- every cross-user attempt is deliberately made
        # using user A's JWT (check 6), so B never needs to authenticate.
        sign_in(client, email_b, password)

        try:
            # users rows are auto-created by a trigger in 001_initial.sql
            # per prior tickets' precedent; wardrobe_items only needs
            # user_id to exist as an auth.users row (FK target), not a
            # public.users row -- but insert defensively via service_role
            # in case that trigger doesn't fire for admin-created users.
            client.post(
                f"{REST_URL}/users",
                headers={**admin_headers(), "Prefer": "resolution=ignore-duplicates"},
                json={"id": user_a, "plan_tier": "free"},
            )
            client.post(
                f"{REST_URL}/users",
                headers={**admin_headers(), "Prefer": "resolution=ignore-duplicates"},
                json={"id": user_b, "plan_tier": "free"},
            )

            item_a = str(uuid.uuid4())
            item_b = str(uuid.uuid4())
            resp = client.post(
                f"{REST_URL}/wardrobe_items",
                headers=admin_headers(),
                json={
                    "id": item_a,
                    "user_id": user_a,
                    "category": "western_top",
                    "purchase_price": 1000,
                    "processing_status": "uploaded",
                    "image_url": f"wardrobe/{user_a}/{item_a}/original.jpg",
                },
            )
            resp.raise_for_status()
            resp = client.post(
                f"{REST_URL}/wardrobe_items",
                headers=admin_headers(),
                json={
                    "id": item_b,
                    "user_id": user_b,
                    "category": "western_top",
                    "purchase_price": 500,
                    "processing_status": "uploaded",
                    "image_url": f"wardrobe/{user_b}/{item_b}/original.jpg",
                },
            )
            resp.raise_for_status()

            def get_item(item_id: str) -> dict:
                r = client.get(
                    f"{REST_URL}/wardrobe_items",
                    headers=admin_headers(),
                    params={
                        "id": f"eq.{item_id}",
                        "select": "wear_count,last_worn_at,cost_per_wear",
                    },
                )
                r.raise_for_status()
                return r.json()[0]

            def user_headers(jwt: str) -> dict[str, str]:
                return {
                    "apikey": ANON_KEY,
                    "Authorization": f"Bearer {jwt}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                }

            # --- Check 1: insert a wear -> wear_count=1, last_worn_at set,
            # cost_per_wear = purchase_price / 1.
            r = client.post(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                json={"item_id": item_a, "user_id": user_a, "worn_on": "2026-07-20"},
            )
            check("1a. insert wear returns 201", r.status_code == 201, r.text)
            row = get_item(item_a)
            check("1b. wear_count == 1", row["wear_count"] == 1, str(row))
            check("1c. last_worn_at == 2026-07-20", row["last_worn_at"] == "2026-07-20", str(row))
            check("1d. cost_per_wear == 1000.0", float(row["cost_per_wear"]) == 1000.0, str(row))

            # --- Check 2: insert a second, EARLIER wear -> wear_count=2,
            # last_worn_at unchanged (MAX, not "latest inserted").
            r = client.post(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                json={"item_id": item_a, "user_id": user_a, "worn_on": "2026-07-01"},
            )
            check("2a. insert earlier wear returns 201", r.status_code == 201, r.text)
            row = get_item(item_a)
            check("2b. wear_count == 2", row["wear_count"] == 2, str(row))
            check(
                "2c. last_worn_at still 2026-07-20 (MAX, not latest-inserted)",
                row["last_worn_at"] == "2026-07-20",
                str(row),
            )

            # --- Check 3: update a wear's date to a later one -> last_worn_at follows.
            r = client.get(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                params={"item_id": f"eq.{item_a}", "worn_on": "eq.2026-07-01", "select": "id"},
            )
            wear_id = r.json()[0]["id"]
            r = client.patch(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                params={"id": f"eq.{wear_id}"},
                json={"worn_on": "2026-07-25"},
            )
            check("3a. update wear date returns 200", r.status_code == 200, r.text)
            row = get_item(item_a)
            check(
                "3b. last_worn_at follows to 2026-07-25",
                row["last_worn_at"] == "2026-07-25",
                str(row),
            )

            # --- Check 5 (duplicate): same-day insert collapses (ON CONFLICT
            # no-op at the app layer; a raw insert here hits the unique
            # violation directly since this script bypasses ON CONFLICT).
            r = client.post(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                json={"item_id": item_a, "user_id": user_a, "worn_on": "2026-07-25"},
            )
            check("5a. duplicate same-day insert rejected (23505)", r.status_code == 409, r.text)
            row_before = get_item(item_a)
            check(
                "5b. wear_count unchanged after rejected duplicate",
                row_before["wear_count"] == 2,
                str(row_before),
            )

            # --- Check 6: cross-user integrity -- user A attempts to insert
            # a wear referencing user B's item_id.
            r = client.post(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                json={"item_id": item_b, "user_id": user_a, "worn_on": "2026-07-20"},
            )
            check(
                "6a. cross-user wear (A's user_id, B's item_id) rejected",
                r.status_code in (400, 403, 404, 409),
                r.text,
            )
            r = client.post(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                json={"item_id": item_b, "user_id": user_b, "worn_on": "2026-07-20"},
            )
            check(
                "6b. cross-user wear (A's JWT, B's user_id/item_id) rejected by RLS WITH CHECK",
                r.status_code in (400, 403, 404, 409),
                r.text,
            )
            row_b = get_item(item_b)
            check(
                "6c. user B's wear_count unchanged (still 0)", row_b["wear_count"] == 0, str(row_b)
            )

            # --- Check 4: delete all wears -> wear_count=0, last_worn_at
            # NULL, cost_per_wear falls back to purchase_price.
            r = client.delete(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                params={"item_id": f"eq.{item_a}"},
            )
            check("4a. delete all wears returns 200", r.status_code == 200, r.text)
            row = get_item(item_a)
            check("4b. wear_count == 0", row["wear_count"] == 0, str(row))
            check("4c. last_worn_at is None", row["last_worn_at"] is None, str(row))
            check(
                "4d. cost_per_wear falls back to purchase_price (1000.0)",
                float(row["cost_per_wear"]) == 1000.0,
                str(row),
            )

            # --- Check 7: delete the parent item -> its wear rows are gone.
            r = client.post(
                f"{REST_URL}/wardrobe_item_wears",
                headers=user_headers(jwt_a),
                json={"item_id": item_a, "user_id": user_a, "worn_on": "2026-07-26"},
            )
            check("7a. re-insert a wear for the cascade check", r.status_code == 201, r.text)
            r = client.delete(
                f"{REST_URL}/wardrobe_items",
                headers=admin_headers(),
                params={"id": f"eq.{item_a}"},
            )
            check("7b. delete parent item returns 204", r.status_code == 204, r.text)
            r = client.get(
                f"{REST_URL}/wardrobe_item_wears",
                headers=admin_headers(),
                params={"item_id": f"eq.{item_a}"},
            )
            check("7c. wear rows cascaded away (empty list)", r.json() == [], r.text)

        finally:
            # Cleanup: delete leftover wardrobe_items/users rows + auth users.
            client.delete(
                f"{REST_URL}/wardrobe_items",
                headers=admin_headers(),
                params={"user_id": f"in.({user_a},{user_b})"},
            )
            client.delete(
                f"{REST_URL}/users",
                headers=admin_headers(),
                params={"id": f"in.({user_a},{user_b})"},
            )
            delete_user(client, user_a)
            delete_user(client, user_b)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
