"""Schema verification tests for SS-002 (Supabase Project Setup & Schema Migration).

These verify the *live* Postgres schema behind the linked Supabase project
(`mefpfykuinasgkpfhmzk`, applied via `supabase/migrations/001_initial.sql`)
actually satisfies the ticket's acceptance criteria:

- all 7 tables exist
- the 2 surviving ENUMs exist with the exact value sets from the migration
  (`occasion_type` was dropped by SS-025 -- its absence is asserted instead)
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

# (SS-025) These are no longer ENUM labels -- the `occasion_type` type was
# dropped by 009_drop_occasion_type_and_merge_taxonomy.sql. They are the 12
# rows seeded into the `occasions` REGISTRY by 007_occasions_registry.sql, in
# `sort_order` (which reproduces the retired enum's declaration order, so
# every shipped picker renders in exactly the order it did before).
EXPECTED_OCCASION_KEYS = [
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

# The value set of `occasions.badge_color`'s CHECK -- identical to Badge's
# OccasionKey union in mobile/components/ui/Badge.tsx.
EXPECTED_BADGE_COLORS = {"wedding", "office", "festival", "casual"}

EXPECTED_OCCASION_ALIASES = {
    "wedding": "wedding_guest",
    "date": "date_night",
    "work": "office",
    "gym": "workout",
    "pooja": "puja",
    "vacation": "travel",
    "formal": "formal_event",
    "everyday": "casual",
}

EXPECTED_OCCASION_TABLES = {"occasions", "occasion_aliases", "occasion_unknown_tags"}


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

    assert len(wardrobe_category) == 21
    assert wardrobe_category == EXPECTED_WARDROBE_CATEGORY
    assert len(plan_tier) == 3
    assert plan_tier == EXPECTED_PLAN_TIER


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


# ==========================================================================
# SS-025 -- Occasion Taxonomy & Extensibility Migration (007/008/009)
#
# Like the rest of this module, these are SKIPPED unless psycopg2 and
# SUPABASE_DB_URL are both available. Every write below is rolled back by
# the db_conn fixture, so none of them persists against the live project.
# ==========================================================================


def test_occasion_type_enum_no_longer_exists(db_conn: Any) -> None:
    """The drift guard now guards the type's ABSENCE. `_occasion_type` (the
    implicit array type) must be gone too -- it is dropped with the base
    type, so a leftover would mean 009 did not complete."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT typname FROM pg_type WHERE typname IN ('occasion_type', '_occasion_type')"
        )
        rows = cur.fetchall()

    assert rows == [], f"occasion_type should have been dropped by 009, found: {rows}"


def test_occasion_types_onboarding_table_no_longer_exists(db_conn: Any) -> None:
    """009 drops the superseded 9-row onboarding taxonomy table. Its content
    is fully reconstructible from 003_onboarding_taxonomies.sql, transcribed
    verbatim into 009's rollback block."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'occasion_types'
            """
        )
        assert cur.fetchone() is None


def test_occasion_registry_tables_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(EXPECTED_OCCASION_TABLES),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == EXPECTED_OCCASION_TABLES


def test_occasions_seeded_with_exactly_the_twelve_canonical_keys(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute("SELECT key FROM occasions ORDER BY sort_order")
        keys = [row[0] for row in cur.fetchall()]

    assert len(keys) == 12
    assert keys == EXPECTED_OCCASION_KEYS


def test_every_occasion_has_a_badge_color_from_the_four_token_set(db_conn: Any) -> None:
    """The BL-008 STRUCTURAL assertion: the 4-of-12 colour gap cannot recur,
    because `badge_color` is NOT NULL with a CHECK against Badge's four
    occasion tokens. No occasion can exist without a colour."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT key, badge_color FROM occasions")
        rows = cur.fetchall()

    assert rows, "occasions table is empty"
    missing = [key for key, colour in rows if colour is None]
    assert not missing, f"occasions with no badge_color: {missing}"
    out_of_set = [(k, c) for k, c in rows if c not in EXPECTED_BADGE_COLORS]
    assert not out_of_set, f"badge_color outside the token set: {out_of_set}"


def test_badge_color_check_rejects_an_arbitrary_hex(db_conn: Any) -> None:
    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO occasions (key, label, kind, formality, badge_color)
            VALUES ('bad_colour_probe', 'Probe', 'social', 5, '#FF0000')
            """
        )


def test_occasion_aliases_seeded_and_disjoint_from_occasion_keys(db_conn: Any) -> None:
    """key/alias disjointness has NO cross-table constraint by design -- it
    is enforced by resolution order (canonical key wins) plus this test. Do
    not "fix" a failure here by adding a trigger; fix the data."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT alias, occasion_key FROM occasion_aliases")
        aliases = dict(cur.fetchall())
        cur.execute("SELECT key FROM occasions")
        keys = {row[0] for row in cur.fetchall()}

    assert aliases == EXPECTED_OCCASION_ALIASES
    assert not (set(aliases) & keys), (
        f"alias/key collision: {set(aliases) & keys} -- inert by resolution "
        "order, but it should not exist"
    )


def test_region_and_culture_scope_reject_the_empty_array(db_conn: Any) -> None:
    """NULL means UNIVERSAL. The empty array is forbidden precisely so nobody
    can write "applies nowhere" and get an occasion that silently never
    matches."""
    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO occasions (key, label, kind, formality, badge_color, region_scope)
            VALUES ('empty_region_probe', 'Probe', 'social', 5, 'casual', '{}')
            """
        )


def test_seeded_occasions_all_ship_universal_scope(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM occasions "
            "WHERE region_scope IS NOT NULL OR culture_scope IS NOT NULL"
        )
        (scoped,) = cur.fetchone()

    assert scoped == 0, "all 12 seed rows ship NULL (universal) region/culture scope"


def test_wardrobe_occasion_tags_is_now_a_text_array(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type, udt_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'wardrobe_items'
              AND column_name = 'occasion_tags'
            """
        )
        row = cur.fetchone()

    assert row is not None
    data_type, udt_name = row
    assert data_type == "ARRAY"
    assert udt_name == "_text"


def test_scalar_occasion_columns_are_now_text(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, data_type FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name = 'occasion'
              AND table_name IN ('outfits', 'suggestion_sessions', 'social_posts')
            ORDER BY table_name
            """
        )
        rows = cur.fetchall()

    assert len(rows) == 3
    assert all(data_type == "text" for _, data_type in rows), rows


def test_rls_enabled_on_the_three_occasion_tables(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            """,
            (list(EXPECTED_OCCASION_TABLES),),
        )
        rls_by_table = dict(cur.fetchall())

    assert set(rls_by_table) == EXPECTED_OCCASION_TABLES
    disabled = [table for table, enabled in rls_by_table.items() if not enabled]
    assert not disabled, f"RLS not enabled on: {disabled}"


def test_only_select_policies_exist_on_the_occasion_tables(db_conn: Any) -> None:
    """Absence of a write policy IS the write-protection mechanism (design
    section 3.5). A permissive INSERT/UPDATE/DELETE policy appearing here is
    a regression, not a fix."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT tablename, cmd FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            (list(EXPECTED_OCCASION_TABLES),),
        )
        policies = {(table, cmd) for table, cmd in cur.fetchall()}

    assert policies == {
        ("occasions", "SELECT"),
        ("occasion_aliases", "SELECT"),
    }


def test_normalisation_functions_are_security_definer_with_a_pinned_search_path(
    db_conn: Any,
) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.proname, p.prosecdef, p.proconfig
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname LIKE 'occasion_%%'
            """
        )
        rows = {name: (secdef, config) for name, secdef, config in cur.fetchall()}

    for name in (
        "occasion_normalize_one",
        "occasion_normalize_array",
        "occasion_is_known",
        "occasion_log_unknown",
    ):
        assert name in rows, f"{name} is missing"
        secdef, config = rows[name]
        assert secdef is True, f"{name} must be SECURITY DEFINER"
        assert config and any(
            c.startswith("search_path=") for c in config
        ), f"{name} must pin search_path"


def test_normalisation_maps_aliases_dedupes_and_keeps_unknowns(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute("SELECT public.occasion_normalize_one(%s)", ("  Wedding Guest ",))
        assert cur.fetchone()[0] == "wedding_guest"

        cur.execute("SELECT public.occasion_normalize_one(%s)", ("wedding",))
        assert cur.fetchone()[0] == "wedding_guest"

        cur.execute("SELECT public.occasion_normalize_one(%s)", ("Ganesh-Chaturthi!!",))
        assert cur.fetchone()[0] == "ganesh_chaturthi"

        cur.execute(
            "SELECT public.occasion_normalize_array(%s, 'test', NULL)",
            (["Travel", "wedding", "travel", "Sangeet Night"],),
        )
        assert cur.fetchone()[0] == ["travel", "wedding_guest", "sangeet_night"]

        cur.execute("SELECT public.occasion_normalize_array(NULL, 'test', NULL)")
        assert cur.fetchone()[0] is None

        cur.execute("SELECT public.occasion_normalize_array('{}', 'test', NULL)")
        assert cur.fetchone()[0] == []


def test_canonical_key_wins_over_a_colliding_alias(db_conn: Any) -> None:
    """Resolution order is the ONLY thing that makes an alias/key collision
    inert, since Postgres has no cross-table CHECK. Prove it directly."""
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO occasion_aliases (alias, occasion_key) VALUES ('festival', 'party')"
        )
        cur.execute("SELECT public.occasion_normalize_one('festival')")
        assert cur.fetchone()[0] == "festival"


def test_wardrobe_items_trigger_normalises_occasion_tags_on_write(db_conn: Any) -> None:
    """The DB-level backstop under the application normalisers -- what makes
    the three write paths that don't exist yet honestly covered."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wardrobe_items (image_url, category, occasion_tags)
            VALUES (%s, 'western_top', %s)
            RETURNING occasion_tags
            """,
            (
                f"https://example.com/{uuid.uuid4()}.jpg",
                [
                    "  Wedding Guest ",
                    "wedding",
                    "Date",
                    "Sangeet Night",
                    "travel",
                    "travel",
                ],
            ),
        )
        (tags,) = cur.fetchone()

    assert tags == ["wedding_guest", "date_night", "sangeet_night", "travel"]


def test_unknown_tag_write_is_captured_rather_than_dropped(db_conn: Any) -> None:
    probe_slug = f"probe_{uuid.uuid4().hex[:8]}"
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wardrobe_items (image_url, category, occasion_tags)
            VALUES (%s, 'western_top', %s)
            RETURNING occasion_tags
            """,
            (f"https://example.com/{uuid.uuid4()}.jpg", [probe_slug]),
        )
        (tags,) = cur.fetchone()

        cur.execute(
            "SELECT occurrences, sample_source FROM occasion_unknown_tags WHERE slug = %s",
            (probe_slug,),
        )
        row = cur.fetchone()

    assert tags == [probe_slug], "an unknown tag must never be dropped from the column"
    assert row is not None, "unknown slug was not captured"
    assert row[0] == 1
    assert row[1] == "wardrobe_items"


# ==========================================================================
# SS-029 -- Cost & Capacity Ledger (012_ai_cost_ledger.sql)
#
# Like the rest of this module, SKIPPED unless psycopg2 and SUPABASE_DB_URL
# are both available -- QA must state that plainly rather than reporting a
# pass (BL-005).
# ==========================================================================


def test_ai_cost_ledger_table_exists_with_generated_cost_paise_column(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, is_generated
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'ai_cost_ledger'
              AND column_name IN ('cost_micropaise', 'cost_paise')
            """
        )
        rows = dict(cur.fetchall())

    assert rows.get("cost_micropaise") == "NEVER"
    assert rows.get("cost_paise") == "ALWAYS"


def test_ai_cost_ledger_indexes_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'ai_cost_ledger'
            """
        )
        indexes = {row[0] for row in cur.fetchall()}

    assert {
        "idx_ai_cost_ledger_user_created",
        "idx_ai_cost_ledger_request",
        "idx_ai_cost_ledger_feature",
    } <= indexes


def test_ai_cost_ledger_rls_enabled_with_zero_policies_for_anon_or_authenticated(
    db_conn: Any,
) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'ai_cost_ledger'
            """
        )
        (rls_enabled,) = cur.fetchone()

        cur.execute(
            "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = 'ai_cost_ledger'"
        )
        (policy_count,) = cur.fetchone()

    assert rls_enabled is True
    assert policy_count == 0, "ai_cost_ledger must have ZERO policies -- service_role only"


def test_ai_cost_breakdown_view_exists(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.views
            WHERE table_schema = 'public' AND table_name = 'ai_cost_breakdown'
            """
        )
        assert cur.fetchone() is not None


def test_cost_per_wear_still_computes_after_the_table_rewrite(db_conn: Any) -> None:
    """008's ALTER COLUMN ... TYPE rewrites wardrobe_items. cost_per_wear is
    a GENERATED ... STORED column on that same table -- re-verified rather
    than assumed (SS-015 regression adjacency)."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wardrobe_items (image_url, category, purchase_price, wear_count)
            VALUES (%s, 'western_top', 1000, 4)
            RETURNING cost_per_wear
            """,
            (f"https://example.com/{uuid.uuid4()}.jpg",),
        )
        (cost_per_wear,) = cur.fetchone()

    assert cost_per_wear == 250
