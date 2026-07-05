"""Schema verification tests for SS-002 (Supabase Project Setup & Schema Migration).

These verify the *live* Postgres schema behind the linked Supabase project
(`mefpfykuinasgkpfhmzk`, applied via `supabase/migrations/001_initial.sql`)
actually satisfies the ticket's acceptance criteria:

- all 7 tables exist
- all 3 ENUMs exist with the exact value sets from the migration
- RLS is enabled (`pg_class.relrowsecurity`) on every table
- the GIN index on `wardrobe_items.occasion_tags` exists
- `cost_per_wear` is computed correctly by the generated column
- RLS actually denies a cross-user read of `wardrobe_items`

Why these need a *direct* Postgres connection (not the `supabase` Python
client already in requirements.txt): the `supabase`/`postgrest` packages talk
to the project over PostgREST, which only exposes `public` schema
tables/views/RPCs -- there is no built-in way to query `pg_catalog` /
`information_schema` or flip `SET ROLE` through it. Direct inspection needs
`psycopg2` and a Postgres connection string.

**Status as of the SS-002 Developer phase:** neither `psycopg2` nor a
`SUPABASE_DB_URL` connection string is available in this environment, so
this whole module is *skipped* (not failed) at collection time. It is
written to be correct and runnable as-is once someone has:

1. `pip install psycopg2-binary` in `backend/venv`, and
2. `SUPABASE_DB_URL` set to the project's direct Postgres connection string
   (Supabase Dashboard -> Project Settings -> Database -> Connection string,
   "URI" tab; use the `postgres` role so `SET ROLE authenticated` in
   `test_rls_denies_cross_user_read` is permitted).

See docs/worklog/SS-002.md for the full writeup of this gap.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2",
    reason="psycopg2 is not installed; schema verification tests need a real Postgres driver",
)

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

pytestmark = pytest.mark.skipif(
    not SUPABASE_DB_URL,
    reason=(
        "SUPABASE_DB_URL is not set; these tests require a live connection to the "
        "Supabase Postgres instance (see docs/tickets/SS-002-design.md and "
        "docs/worklog/SS-002.md)."
    ),
)

EXPECTED_TABLES = {
    "users",
    "wardrobe_items",
    "outfits",
    "suggestion_sessions",
    "user_avatars",
    "social_posts",
    "shopping_wishlist",
}

EXPECTED_WARDROBE_CATEGORY = [
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

EXPECTED_PLAN_TIER = ["free", "premium", "premium_annual"]

EXPECTED_OCCASION_TYPE = [
    "office",
    "casual",
    "date_night",
    "wedding_guest",
    "festival",
    "puja",
    "party",
    "travel",
    "workout",
    "beach",
    "formal_event",
    "college",
]


@pytest.fixture
def db_conn() -> Iterator[Any]:
    """A direct Postgres connection with every change rolled back on teardown.

    Connecting as the `postgres` role (superuser-equivalent in Supabase) is
    assumed so that `SET ROLE authenticated` works in the RLS test below.
    """
    conn = psycopg2.connect(SUPABASE_DB_URL)
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_all_seven_tables_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(EXPECTED_TABLES),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == EXPECTED_TABLES, f"missing tables: {EXPECTED_TABLES - found}"


def test_enums_have_full_value_set(db_conn: Any) -> None:
    def enum_values(cur: Any, type_name: str) -> list[str]:
        cur.execute(
            """
            SELECT e.enumlabel
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            WHERE t.typname = %s
            ORDER BY e.enumsortorder
            """,
            (type_name,),
        )
        return [row[0] for row in cur.fetchall()]

    with db_conn.cursor() as cur:
        wardrobe_category = enum_values(cur, "wardrobe_category")
        plan_tier = enum_values(cur, "plan_tier")
        occasion_type = enum_values(cur, "occasion_type")

    assert len(wardrobe_category) == 21
    assert wardrobe_category == EXPECTED_WARDROBE_CATEGORY
    assert len(plan_tier) == 3
    assert plan_tier == EXPECTED_PLAN_TIER
    assert len(occasion_type) == 12
    assert occasion_type == EXPECTED_OCCASION_TYPE


def test_rls_enabled_on_all_tables(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            """,
            (list(EXPECTED_TABLES),),
        )
        rls_by_table = dict(cur.fetchall())

    assert set(rls_by_table) == EXPECTED_TABLES
    disabled = [table for table, enabled in rls_by_table.items() if not enabled]
    assert not disabled, f"RLS not enabled on: {disabled}"


def test_wardrobe_occasion_tags_gin_index_exists(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'wardrobe_items'
              AND indexname = 'idx_wardrobe_occasions'
            """
        )
        row = cur.fetchone()

    assert row is not None, "idx_wardrobe_occasions index not found on wardrobe_items"
    indexdef = row[0].lower()
    assert "using gin" in indexdef
    assert "occasion_tags" in indexdef


def test_cost_per_wear_computed_correctly(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wardrobe_items (image_url, category, purchase_price, wear_count)
            VALUES (%s, 'western_top', 1000, 4)
            RETURNING cost_per_wear
            """,
            (f"https://example.com/{uuid.uuid4()}.jpg",),
        )
        (cost_per_wear_worn,) = cur.fetchone()

        cur.execute(
            """
            INSERT INTO wardrobe_items (image_url, category, purchase_price, wear_count)
            VALUES (%s, 'western_top', 1000, 0)
            RETURNING cost_per_wear
            """,
            (f"https://example.com/{uuid.uuid4()}.jpg",),
        )
        (cost_per_wear_unworn,) = cur.fetchone()

    # purchase_price=1000, wear_count=4 -> 1000 / 4
    assert cost_per_wear_worn == 250
    # wear_count=0 -> ELSE branch returns purchase_price unchanged
    assert cost_per_wear_unworn == 1000


def test_rls_denies_cross_user_read(db_conn: Any) -> None:
    """Simulates two distinct authenticated users via the same technique
    Supabase's PostgREST layer uses: `SET ROLE authenticated` plus a
    `request.jwt.claims` GUC carrying the caller's `sub` (user id), which
    `auth.uid()` reads from inside RLS policies.

    Assumes Supabase's default privilege grants (`GRANT ... TO authenticated`)
    are in place for the `public` schema, which Supabase applies automatically
    to new projects/tables.
    """
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email) VALUES (%s, %s), (%s, %s)",
            (
                user_a,
                f"{user_a}@test.stylesense.invalid",
                user_b,
                f"{user_b}@test.stylesense.invalid",
            ),
        )
        cur.execute(
            """
            INSERT INTO wardrobe_items (user_id, image_url, category)
            VALUES (%s, %s, 'western_top')
            """,
            (user_b, f"https://example.com/{uuid.uuid4()}.jpg"),
        )

        cur.execute("SET ROLE authenticated")
        try:
            cur.execute(
                "SET request.jwt.claims = %s",
                (f'{{"sub": "{user_a}", "role": "authenticated"}}',),
            )
            cur.execute("SELECT * FROM wardrobe_items WHERE user_id = %s", (user_b,))
            rows_visible_to_a = cur.fetchall()
        finally:
            cur.execute("RESET ROLE")

    assert rows_visible_to_a == [], (
        "RLS should prevent user A from reading user B's wardrobe_items row, "
        f"but {len(rows_visible_to_a)} row(s) were visible"
    )
