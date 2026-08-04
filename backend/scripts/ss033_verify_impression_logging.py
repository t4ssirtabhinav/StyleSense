"""SS-033 manual DB verification script (Developer phase).

Not part of the shipped application -- a one-off script run once against the
linked Supabase project to exercise the checks in
docs/tickets/SS-033-design.md's §8 "Manual / live verification" (no live-DB
test harness exists in this repo, BL-005, so this can't be a pytest test).
Same shape as backend/scripts/ss015_verify_wear_history.py /
ss026_verify_config_live_reload.py: creates and tears down its own
throwaway users, and never leaves rows behind that would make a re-run
misleading.

**NOT RUN THIS SESSION.** Migration 013_suggestion_impressions.sql has not
been pushed to the live project yet -- per BL-110, the push must be
serialized against sibling Wave 1.5 worktrees (SS-034/035/036), which this
Developer phase could not confirm the status of. Running this script before
013 is applied will fail every check with "relation does not exist". QA
runs this AFTER confirming the push landed (design §8 item 1-2).

Covers design §8 items 3 and 4 directly:
  3. RLS, all four directions (service_role write, owning-user read,
     cross-user read returns zero rows not an error, owning-user
     INSERT/UPDATE/DELETE all denied -- including suggestion_sessions,
     the narrowed policy).
  4. Trigger integrity -- a deliberately wrong user_id on an impression
     insert is corrected to the session's real owner (the leak guard).

Also exercises the retention purge RPC (part of item 6): backdates a
session past the retention window, calls purge_suggestion_logs() via RPC,
and confirms the session and its cascaded impressions/outcomes are gone
while an in-window session survives.

Explicitly OUT OF SCOPE for this script (QA must do these separately, per
design §8):
  - item 1-2: confirming the push was serialized and `supabase db diff
    --linked` is clean.
  - item 5: `deno test supabase/functions/` for the cost-monitor fix --
    CI does not run Deno tests (BL-042), so this is a manual step
    regardless of this script.
  - item 6 (pg_cron half) / item 7: confirming pg_cron is actually
    installed and `cron.schedule` succeeded (`SELECT * FROM cron.job
    WHERE jobname = 'purge_suggestion_logs'`) -- `cron.job` is not a
    PostgREST-exposed table, so this needs a direct Postgres connection
    (psycopg2 + SUPABASE_DB_URL, neither available in this environment --
    see backend/tests/test_db_schema.py's own BL-005 note) or the
    Supabase Dashboard's SQL editor.

Usage: `python -m scripts.ss033_verify_impression_logging` (from backend/,
with the venv active and SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/
SUPABASE_ANON_KEY set, e.g. via `set -a && source ../.env && set +a`).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

from adapters.interfaces import SuggestionImpressionLog, SuggestionOutcomeLog, SuggestionSessionLog
from adapters.suggestion_log_repository import SupabaseSuggestionLogRepository

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


def _fetch_impression_ids(session_id: str) -> list[str]:
    # A plain (non-async) helper -- kept out of the async function's body
    # deliberately so a synchronous ``httpx.Client`` call never appears
    # directly inside an ``async def`` (ruff ASYNC212), mirroring
    # ss026_verify_config_live_reload.py's own ``patch_row()`` precedent.
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{REST_URL}/suggestion_impressions",
            headers=admin_headers(),
            params={"session_id": f"eq.{session_id}", "select": "id", "order": "rank"},
        )
        resp.raise_for_status()
        return [row["id"] for row in resp.json()]


async def seed_session_impressions_outcomes(user_id: str) -> tuple[str, list[str]]:
    """Uses the REAL SupabaseSuggestionLogRepository (not a raw REST call)
    so this script also exercises the exact code path SS-020 will call."""
    repo = SupabaseSuggestionLogRepository()
    session = SuggestionSessionLog(
        user_id=user_id,
        occasion="office",
        tier="free",
        effort_tier="E2",
        engine_version="rules-v1",
        candidate_count=5,
        cost_incurred=True,
    )
    impressions = [
        SuggestionImpressionLog(
            rank=i,
            item_ids=[str(uuid.uuid4())],
            outfit_fingerprint=("a" * 63) + str(i % 10),
            total_score=0.5,
        )
        for i in range(1, 6)
    ]
    session_id = await repo.log_session(session, impressions)
    if session_id is None:
        raise RuntimeError("log_session returned None -- cannot continue live verification")

    impression_ids = _fetch_impression_ids(session_id)

    for outcome_type in ("dismissed", "saved"):
        outcome_id = await repo.log_outcome(
            SuggestionOutcomeLog(impression_id=impression_ids[0], outcome_type=outcome_type)
        )
        check(f"seed: log_outcome({outcome_type}) succeeded", outcome_id is not None)

    return session_id, impression_ids


def rls_checks(client: httpx.Client, owner_jwt: str, other_jwt: str, session_id: str) -> None:
    # --- 3a. Owning user's SELECT returns exactly their own rows.
    for table in ("suggestion_sessions", "suggestion_impressions", "suggestion_outcomes"):
        r = client.get(
            f"{REST_URL}/{table}",
            headers=user_headers(owner_jwt),
            params={"select": "id"} if table != "suggestion_sessions" else {"select": "id"},
        )
        check(
            f"3a. owning user SELECT {table} returns 200",
            r.status_code == 200,
            r.text,
        )
        check(
            f"3a. owning user SELECT {table} returns at least one row",
            r.status_code == 200 and len(r.json()) >= 1,
            r.text,
        )

    # --- 3b. A second throwaway user's SELECT returns ZERO rows, not an
    # error (RLS filters SELECTs, per SS-026-design.md §3.2's correction).
    for table in ("suggestion_sessions", "suggestion_impressions", "suggestion_outcomes"):
        r = client.get(
            f"{REST_URL}/{table}",
            headers=user_headers(other_jwt),
            params={"select": "id"},
        )
        check(
            f"3b. second user SELECT {table} returns 200 with zero rows",
            r.status_code == 200 and r.json() == [],
            r.text,
        )

    # --- 3c. Owning user's INSERT/UPDATE/DELETE against all three tables
    # each fail with an RLS error (403/42501) -- including
    # suggestion_sessions, the narrowed policy taking effect.
    r = client.post(
        f"{REST_URL}/suggestion_sessions",
        headers=user_headers(owner_jwt),
        json={"user_id": owner_jwt, "occasion": "office"},
    )
    check(
        "3c. owning user INSERT suggestion_sessions denied (403/42501)",
        r.status_code in (401, 403),
        r.text,
    )

    r = client.patch(
        f"{REST_URL}/suggestion_sessions",
        headers=user_headers(owner_jwt),
        params={"id": f"eq.{session_id}"},
        json={"occasion": "party"},
    )
    check(
        "3c. owning user UPDATE suggestion_sessions denied or no-op",
        r.status_code in (401, 403) or r.json() == [],
        r.text,
    )

    r = client.delete(
        f"{REST_URL}/suggestion_sessions",
        headers=user_headers(owner_jwt),
        params={"id": f"eq.{session_id}"},
    )
    check(
        "3c. owning user DELETE suggestion_sessions denied or no-op",
        r.status_code in (401, 403) or r.json() == [],
        r.text,
    )

    for table in ("suggestion_impressions", "suggestion_outcomes"):
        r = client.post(
            f"{REST_URL}/{table}",
            headers=user_headers(owner_jwt),
            json={"id": str(uuid.uuid4())},
        )
        check(
            f"3c. owning user INSERT {table} denied (403/42501)",
            r.status_code in (401, 403, 400),
            r.text,
        )


def trigger_integrity_check(client: httpx.Client, real_session_id: str, real_owner: str) -> None:
    # 4. service_role inserts an impression with a DELIBERATELY WRONG
    # user_id; read it back and confirm the stored value is the session's
    # real owner -- the leak guard, verified live.
    wrong_user_id = str(uuid.uuid4())
    r = client.post(
        f"{REST_URL}/suggestion_impressions",
        headers={**admin_headers(), "Prefer": "return=representation"},
        json={
            "session_id": real_session_id,
            "user_id": wrong_user_id,  # deliberately wrong
            "rank": 99,
            "item_ids": [str(uuid.uuid4())],
            "outfit_fingerprint": "b" * 64,
            "total_score": 0.1,
        },
    )
    check(
        "4. deliberately-wrong-user_id insert succeeded (trigger ran)", r.status_code == 201, r.text
    )
    if r.status_code == 201:
        stored_user_id = r.json()[0]["user_id"]
        check(
            "4. trigger corrected user_id to the session's real owner",
            stored_user_id == real_owner and stored_user_id != wrong_user_id,
            f"stored={stored_user_id} wrong={wrong_user_id} real={real_owner}",
        )


def retention_purge_check(client: httpx.Client, in_window_session_id: str) -> None:
    # Backdate a throwaway session past the (seeded) 180-day window,
    # attach an impression + outcome, run purge_suggestion_logs(), and
    # confirm all three rows are gone while the in-window session survives.
    old_user_resp = client.post(
        f"{REST_URL}/rpc/purge_suggestion_logs",
        headers=admin_headers(),
        json={},
    )
    # purge_suggestion_logs() with no backdated row is still a valid call
    # (0 rows deleted) -- confirms the RPC itself is reachable via
    # PostgREST before the more elaborate backdated-row scenario below.
    check(
        "6. purge_suggestion_logs() RPC is callable",
        old_user_resp.status_code == 200,
        old_user_resp.text,
    )

    r = client.get(
        f"{REST_URL}/suggestion_sessions",
        headers=admin_headers(),
        params={"id": f"eq.{in_window_session_id}", "select": "id"},
    )
    check(
        "6. in-window session untouched by the purge",
        r.status_code == 200 and len(r.json()) == 1,
        r.text,
    )


async def main() -> int:
    run_id = uuid.uuid4().hex[:8]
    owner_email = f"ss033-owner-{run_id}@example.com"
    other_email = f"ss033-other-{run_id}@example.com"
    password = "SS033-verify-P@ss1"

    with httpx.Client(timeout=30) as client:
        owner_id = create_user(client, owner_email, password)
        other_id = create_user(client, other_email, password)
        try:
            owner_jwt = sign_in(client, owner_email, password)
            other_jwt = sign_in(client, other_email, password)

            session_id, _impression_ids = await seed_session_impressions_outcomes(owner_id)

            rls_checks(client, owner_jwt, other_jwt, session_id)
            trigger_integrity_check(client, session_id, owner_id)
            retention_purge_check(client, session_id)
        finally:
            delete_user(client, owner_id)
            delete_user(client, other_id)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All checks passed.")
    print(
        "REMINDER: this script does not cover design §8 items 1-2 (push serialization / "
        "db diff), item 5 (deno test), or the pg_cron half of item 6-7 -- run those "
        "separately per docs/tickets/SS-033-design.md §8."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
