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
        assert config and any(c.startswith("search_path=") for c in config), (
            f"{name} must pin search_path"
        )


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


# ==========================================================================
# SS-033 -- Suggestion Impression & Outcome Logging (013)
#
# Like the rest of this module, these are SKIPPED unless psycopg2 and
# SUPABASE_DB_URL are both available. Every write below is rolled back by
# the db_conn fixture, so none of them persists against the live project.
#
# EXPECTED_SUGGESTION_LOG_TABLES mirrors EXPECTED_OCCASION_TABLES's own
# precedent (SS-025) rather than folding into the shared EXPECTED_TABLES
# constant above -- that constant backs test_all_seven_tables_exist's own
# docstring/name ("all 7 tables exist"), which two more tables would make
# inaccurate.
# ==========================================================================

EXPECTED_SUGGESTION_LOG_TABLES = {"suggestion_impressions", "suggestion_outcomes"}

EXPECTED_NEW_SUGGESTION_SESSIONS_COLUMNS = {
    "engine_version",
    "effort_tier",
    "tier",
    "config_snapshot_hash",
    "candidate_count",
    "request_id",
    "latency_ms",
    "cost_incurred",
    "zero_cost_reason",
}

EXPECTED_NEW_SUGGESTION_SESSIONS_CHECK_CONSTRAINTS = {
    "suggestion_sessions_effort_tier_check",
    "suggestion_sessions_tier_shape_check",
    "suggestion_sessions_candidate_count_check",
    "suggestion_sessions_latency_check",
    "suggestion_sessions_zero_cost_reason_check",
    "suggestion_sessions_cost_marker_consistency_check",
}

# Every index 013_suggestion_impressions.sql names explicitly (design §7.4
# says "seven" -- transcribing the migration's actual CREATE INDEX
# statements yields this larger, exact set; asserting the real set is more
# faithful to the AC's intent than pinning the design doc's own count).
EXPECTED_NEW_SUGGESTION_LOG_INDEXES = {
    "idx_suggestion_impressions_user_created",
    "idx_suggestion_impressions_user_fingerprint",
    "idx_suggestion_impressions_session",
    "idx_suggestion_impressions_item_ids",
    "uq_suggestion_outcomes_dedupe",
    "idx_suggestion_outcomes_impression_order",
    "idx_suggestion_outcomes_user_type_created",
    "idx_suggestion_sessions_costed_created",
    "idx_suggestion_sessions_created",
    "idx_suggestion_sessions_user_created",
}


def _insert_user(cur: Any) -> str:
    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, email) VALUES (%s, %s)",
        (user_id, f"{user_id}@test.stylesense.invalid"),
    )
    return user_id


def _insert_session(cur: Any, user_id: str | None) -> str:
    session_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO suggestion_sessions (id, user_id) VALUES (%s, %s)",
        (session_id, user_id),
    )
    return session_id


def _insert_impression(
    cur: Any,
    session_id: str,
    *,
    rank: int = 1,
    item_ids: list[str] | None = None,
    fingerprint: str | None = None,
) -> str:
    impression_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO suggestion_impressions
          (id, session_id, rank, item_ids, outfit_fingerprint, total_score)
        VALUES (%s, %s, %s, %s, %s, 0.5)
        """,
        (
            impression_id,
            session_id,
            rank,
            item_ids or [str(uuid.uuid4())],
            fingerprint or ("a" * 64),
        ),
    )
    return impression_id


def test_suggestion_log_tables_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(EXPECTED_SUGGESTION_LOG_TABLES),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == EXPECTED_SUGGESTION_LOG_TABLES


def test_new_suggestion_sessions_columns_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'suggestion_sessions'
              AND column_name = ANY(%s)
            """,
            (list(EXPECTED_NEW_SUGGESTION_SESSIONS_COLUMNS),),
        )
        rows = {row[0]: row for row in cur.fetchall()}

    assert set(rows) == EXPECTED_NEW_SUGGESTION_SESSIONS_COLUMNS
    _, is_nullable, default = rows["cost_incurred"]
    assert is_nullable == "NO"
    assert default is not None and "true" in default.lower()


def test_six_new_check_constraints_exist_by_name(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint WHERE conname = ANY(%s)",
            (list(EXPECTED_NEW_SUGGESTION_SESSIONS_CHECK_CONSTRAINTS),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == EXPECTED_NEW_SUGGESTION_SESSIONS_CHECK_CONSTRAINTS


def test_cost_marker_consistency_check_rejects_the_contradictory_pair(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        user_id = _insert_user(cur)

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO suggestion_sessions (user_id, cost_incurred, zero_cost_reason) "
            "VALUES (%s, false, NULL)",
            (user_id,),
        )


def test_deprecated_columns_carry_a_comment_starting_with_deprecated(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname, col_description(a.attrelid, a.attnum)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'suggestion_sessions'
              AND a.attname IN ('suggestions', 'accepted_outfit_id')
            """
        )
        rows = dict(cur.fetchall())

    assert rows.get("suggestions", "").startswith("DEPRECATED")
    assert rows.get("accepted_outfit_id", "").startswith("DEPRECATED")


def test_rls_enabled_on_both_new_suggestion_log_tables(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            """,
            (list(EXPECTED_SUGGESTION_LOG_TABLES),),
        )
        rls_by_table = dict(cur.fetchall())

    assert set(rls_by_table) == EXPECTED_SUGGESTION_LOG_TABLES
    disabled = [table for table, enabled in rls_by_table.items() if not enabled]
    assert not disabled, f"RLS not enabled on: {disabled}"


def test_only_select_policies_exist_on_the_suggestion_log_tables(db_conn: Any) -> None:
    """Absence of a write policy IS the write-protection mechanism (design
    §3.5). A permissive INSERT/UPDATE/DELETE policy appearing here is a
    regression, not a fix."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT tablename, cmd FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            (list(EXPECTED_SUGGESTION_LOG_TABLES),),
        )
        policies = {(table, cmd) for table, cmd in cur.fetchall()}

    assert policies == {
        ("suggestion_impressions", "SELECT"),
        ("suggestion_outcomes", "SELECT"),
    }


def test_suggestion_sessions_policy_is_narrowed_to_read_only(db_conn: Any) -> None:
    """The one non-additive statement in 013 actually landed: the shipped
    FOR ALL user_owns_sessions policy is gone, replaced by a SELECT-only
    one (design §3.5)."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT policyname, cmd FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'suggestion_sessions'"
        )
        policies = dict(cur.fetchall())

    assert policies == {"user_reads_own_sessions": "SELECT"}
    assert "user_owns_sessions" not in policies


def test_new_suggestion_log_indexes_exist_and_the_costed_one_is_partial(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = ANY(%s)
            """,
            (list(EXPECTED_NEW_SUGGESTION_LOG_INDEXES),),
        )
        rows = dict(cur.fetchall())

    assert set(rows) == EXPECTED_NEW_SUGGESTION_LOG_INDEXES
    assert "where" in rows["idx_suggestion_sessions_costed_created"].lower()


def test_user_id_derivation_triggers_are_registered(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT tgname FROM pg_trigger WHERE tgname = ANY(%s)",
            (
                [
                    "trg_suggestion_impressions_set_user_id",
                    "trg_suggestion_outcomes_set_user_id",
                ],
            ),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == {
        "trg_suggestion_impressions_set_user_id",
        "trg_suggestion_outcomes_set_user_id",
    }


def test_impression_trigger_overrides_a_deliberately_wrong_user_id(db_conn: Any) -> None:
    """THE leak guard -- the most important assertion in this module (design
    §7.4). A wrong user_id sent by the writer must be structurally
    impossible to persist; the BEFORE INSERT trigger must overwrite it with
    the session's real owner before the row is ever written."""
    with db_conn.cursor() as cur:
        real_owner = _insert_user(cur)
        session_id = _insert_session(cur, real_owner)
        wrong_user_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO suggestion_impressions
              (session_id, user_id, rank, item_ids, outfit_fingerprint, total_score)
            VALUES (%s, %s, 1, %s, %s, 0.5)
            RETURNING user_id
            """,
            (session_id, wrong_user_id, [str(uuid.uuid4())], "a" * 64),
        )
        (stored_user_id,) = cur.fetchone()

    assert stored_user_id == real_owner
    assert stored_user_id != wrong_user_id


def test_outcome_trigger_derives_user_id_from_the_impression_owner(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        real_owner = _insert_user(cur)
        session_id = _insert_session(cur, real_owner)
        impression_id = _insert_impression(cur, session_id)
        wrong_user_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO suggestion_outcomes (impression_id, user_id, outcome_type)
            VALUES (%s, %s, 'saved')
            RETURNING user_id
            """,
            (impression_id, wrong_user_id),
        )
        (stored_user_id,) = cur.fetchone()

    assert stored_user_id == real_owner
    assert stored_user_id != wrong_user_id


def test_impression_insert_for_a_session_with_a_null_user_id_raises(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        session_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO suggestion_sessions (id, user_id) VALUES (%s, NULL)", (session_id,)
        )

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException):
        cur.execute(
            """
            INSERT INTO suggestion_impressions
              (session_id, rank, item_ids, outfit_fingerprint, total_score)
            VALUES (%s, 1, %s, %s, 0.5)
            """,
            (session_id, [str(uuid.uuid4())], "a" * 64),
        )


def test_suggestion_log_retention_days_defaults_to_180_with_no_config_row(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM app_config WHERE key = 'suggestion_log_retention_days'")
        cur.execute("SELECT public.suggestion_log_retention_days()")
        (days,) = cur.fetchone()

    assert days == 180


def test_suggestion_log_retention_days_clamps_out_of_range_values(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE app_config SET value = '{\"days\": 5}'::jsonb "
            "WHERE key = 'suggestion_log_retention_days'"
        )
        cur.execute("SELECT public.suggestion_log_retention_days()")
        (low,) = cur.fetchone()

        cur.execute(
            "UPDATE app_config SET value = '{\"days\": 5000}'::jsonb "
            "WHERE key = 'suggestion_log_retention_days'"
        )
        cur.execute("SELECT public.suggestion_log_retention_days()")
        (high,) = cur.fetchone()

    assert low == 30
    assert high == 730


def test_suggestion_log_retention_days_degrades_to_180_on_a_malformed_value(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            'UPDATE app_config SET value = \'{"days": "not-a-number"}\'::jsonb '
            "WHERE key = 'suggestion_log_retention_days'"
        )
        cur.execute("SELECT public.suggestion_log_retention_days()")
        (days,) = cur.fetchone()

    assert days == 180


def test_purge_suggestion_logs_deletes_expired_sessions_and_cascades_as_a_unit(
    db_conn: Any,
) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE app_config SET value = '{\"days\": 30}'::jsonb "
            "WHERE key = 'suggestion_log_retention_days'"
        )

        old_owner = _insert_user(cur)
        old_session_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO suggestion_sessions (id, user_id, created_at) "
            "VALUES (%s, %s, now() - interval '40 days')",
            (old_session_id, old_owner),
        )
        old_impression_id = _insert_impression(cur, old_session_id)
        cur.execute(
            "INSERT INTO suggestion_outcomes (impression_id, outcome_type) "
            "VALUES (%s, 'saved') RETURNING id",
            (old_impression_id,),
        )
        (old_outcome_id,) = cur.fetchone()

        recent_owner = _insert_user(cur)
        recent_session_id = _insert_session(cur, recent_owner)

        cur.execute("SELECT sessions_deleted FROM purge_suggestion_logs()")
        (sessions_deleted,) = cur.fetchone()

        cur.execute("SELECT id FROM suggestion_sessions WHERE id = %s", (old_session_id,))
        old_session_gone = cur.fetchone() is None
        cur.execute("SELECT id FROM suggestion_impressions WHERE id = %s", (old_impression_id,))
        old_impression_gone = cur.fetchone() is None
        cur.execute("SELECT id FROM suggestion_outcomes WHERE id = %s", (old_outcome_id,))
        old_outcome_gone = cur.fetchone() is None
        cur.execute("SELECT id FROM suggestion_sessions WHERE id = %s", (recent_session_id,))
        recent_session_survives = cur.fetchone() is not None

    assert sessions_deleted >= 1
    assert old_session_gone, "expired session should have been purged"
    assert old_impression_gone, "cascade should have removed the expired session's impression"
    assert old_outcome_gone, "cascade should have removed the expired impression's outcome"
    assert recent_session_survives, "an in-window session must not be touched by the purge"


def test_array_length_check_rejects_an_empty_item_ids_array(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO suggestion_impressions
              (session_id, rank, item_ids, outfit_fingerprint, total_score)
            VALUES (%s, 1, %s, %s, 0.5)
            """,
            (session_id, [], "a" * 64),
        )


def test_outfit_fingerprint_check_rejects_the_wrong_shape(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO suggestion_impressions
              (session_id, rank, item_ids, outfit_fingerprint, total_score)
            VALUES (%s, 1, %s, 'NOT-A-VALID-HASH', 0.5)
            """,
            (session_id, [str(uuid.uuid4())]),
        )


def test_unique_session_rank_constraint_rejects_a_duplicate_rank(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)
        _insert_impression(cur, session_id, rank=1)

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
        _insert_impression(cur, session_id, rank=1)


def test_dedupe_partial_unique_index_rejects_a_duplicate_key(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)
        impression_id = _insert_impression(cur, session_id)
        cur.execute(
            "INSERT INTO suggestion_outcomes (impression_id, outcome_type, dedupe_key) "
            "VALUES (%s, 'saved', 'retry-key-1')",
            (impression_id,),
        )

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO suggestion_outcomes (impression_id, outcome_type, dedupe_key) "
            "VALUES (%s, 'saved', 'retry-key-1')",
            (impression_id,),
        )


def test_dedupe_partial_unique_index_permits_two_null_dedupe_keys(db_conn: Any) -> None:
    """NULL is unconstrained -- the AC's own 'dismisses then later saves the
    same outfit' case must not be blocked (design §3.4)."""
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)
        impression_id = _insert_impression(cur, session_id)

        cur.execute(
            "INSERT INTO suggestion_outcomes (impression_id, outcome_type) VALUES (%s, 'dismissed')",
            (impression_id,),
        )
        cur.execute(
            "INSERT INTO suggestion_outcomes (impression_id, outcome_type) VALUES (%s, 'saved')",
            (impression_id,),
        )
        cur.execute(
            "SELECT count(*) FROM suggestion_outcomes WHERE impression_id = %s", (impression_id,)
        )
        (count,) = cur.fetchone()

    assert count == 2


def test_deleting_a_wardrobe_item_leaves_its_impressions_intact(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)
        item_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO wardrobe_items (id, user_id, image_url, category) "
            "VALUES (%s, %s, %s, 'western_top')",
            (item_id, owner, f"https://example.com/{uuid.uuid4()}.jpg"),
        )
        impression_id = _insert_impression(cur, session_id, item_ids=[item_id])

        cur.execute("DELETE FROM wardrobe_items WHERE id = %s", (item_id,))

        cur.execute("SELECT item_ids FROM suggestion_impressions WHERE id = %s", (impression_id,))
        (item_ids,) = cur.fetchone()

    assert item_ids == [item_id], "a deleted wardrobe item must not erase impression history"


def test_deleting_an_outfit_nulls_the_outcome_outfit_id_and_keeps_the_row(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        session_id = _insert_session(cur, owner)
        impression_id = _insert_impression(cur, session_id)
        outfit_id = str(uuid.uuid4())
        cur.execute("INSERT INTO outfits (id, user_id) VALUES (%s, %s)", (outfit_id, owner))
        cur.execute(
            "INSERT INTO suggestion_outcomes (impression_id, outcome_type, outfit_id) "
            "VALUES (%s, 'saved', %s) RETURNING id",
            (impression_id, outfit_id),
        )
        (outcome_id,) = cur.fetchone()

        cur.execute("DELETE FROM outfits WHERE id = %s", (outfit_id,))

        cur.execute("SELECT outfit_id FROM suggestion_outcomes WHERE id = %s", (outcome_id,))
        (stored_outfit_id,) = cur.fetchone()

    assert stored_outfit_id is None, "the saved fact must survive even if the outfit is deleted"


# ==========================================================================
# SS-034 -- Garment Types Registry (EXPAND phase only, 014)
#
# Like the rest of this module, these are SKIPPED unless psycopg2 and
# SUPABASE_DB_URL are both available. Every write below is rolled back by
# the db_conn fixture, so none of them persists against the live project.
#
# Nothing in backend/ or mobile/ reads garment_types yet -- that AC is
# covered by the separate, unconditionally-run
# test_garment_registry_purely_additive.py, not by anything here.
# ==========================================================================

EXPECTED_GARMENT_TYPE_TABLES = {
    "garment_types",
    "garment_type_aliases",
    "garment_unknown_types",
    "garment_set_components",
}

# The 10 B.2 [VERIFIED] ethnic bottoms (design §3.5 / §6.1).
EXPECTED_TEN_SOURCED_ETHNIC_BOTTOMS = {
    "palazzo",
    "churidar",
    "sharara",
    "patiala_salwar",
    "gharara",
    "dhoti_pants",
    "cigarette_pants",
    "culottes",
    "leggings",
    "salwar",
}


def test_garment_registry_tables_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(EXPECTED_GARMENT_TYPE_TABLES),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == EXPECTED_GARMENT_TYPE_TABLES


def test_garment_types_slot_check_is_closed(db_conn: Any) -> None:
    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO garment_types (key, label, slot, layer, register, base_formality)
            VALUES ('bogus_slot_probe', 'Probe', 'bogus', 0, ARRAY['ethnic'], 5)
            """
        )
    db_conn.rollback()

    # 'set' is the 12th value -- prove it actually landed (design §3.1 deviation).
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO garment_types (key, label, slot, layer, register, base_formality)
            VALUES ('set_slot_probe', 'Probe', 'set', 0, ARRAY['ethnic'], 5)
            RETURNING slot
            """
        )
        (slot,) = cur.fetchone()

    assert slot == "set"


def test_garment_types_parent_key_self_reference_rejected(db_conn: Any) -> None:
    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("UPDATE garment_types SET parent_key = key WHERE key = 'kurta'")


def test_garment_types_region_and_culture_scope_reject_empty_array(db_conn: Any) -> None:
    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO garment_types (key, label, slot, layer, register, base_formality, region_scope)
            VALUES ('empty_region_probe', 'Probe', 'legs', 0, ARRAY['ethnic'], 5, '{}')
            """
        )
    db_conn.rollback()

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO garment_types (key, label, slot, layer, register, base_formality, culture_scope)
            VALUES ('empty_culture_probe', 'Probe', 'legs', 0, ARRAY['ethnic'], 5, '{}')
            """
        )
    db_conn.rollback()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO garment_types (key, label, slot, layer, register, base_formality, region_scope)
            VALUES ('null_region_probe', 'Probe', 'legs', 0, ARRAY['ethnic'], 5, NULL)
            RETURNING region_scope
            """
        )
        (region_scope,) = cur.fetchone()

    assert region_scope is None


def test_garment_types_register_rejects_empty_array(db_conn: Any) -> None:
    """The §3.1 deviation from the proposal's DDL sketch: register TEXT[]
    NOT NULL alone would still permit '{}' (a silent "no register" hole).
    The added CHECK closes it."""
    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO garment_types (key, label, slot, layer, register, base_formality)
            VALUES ('empty_register_probe', 'Probe', 'legs', 0, '{}', 5)
            """
        )


def test_garment_type_aliases_seeded_and_disjoint_from_garment_keys(db_conn: Any) -> None:
    """key/alias disjointness has NO cross-table constraint by design -- it
    is enforced by resolution order (canonical key wins) plus this test."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT alias FROM garment_type_aliases")
        aliases = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT key FROM garment_types")
        keys = {row[0] for row in cur.fetchall()}

    assert aliases, "garment_type_aliases seed is empty"
    assert not (aliases & keys), (
        f"alias/key collision: {aliases & keys} -- inert by resolution order, "
        "but it should not exist"
    )


def test_garment_normalize_one_resolves_key_before_alias(db_conn: Any) -> None:
    """Resolution order is the ONLY thing that makes an alias/key collision
    inert, since Postgres has no cross-table CHECK. Prove it directly, same
    as 007's occasion precedent."""
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO garment_type_aliases (alias, garment_key) VALUES ('palazzo', 'churidar')"
        )
        cur.execute("SELECT public.garment_normalize_one('palazzo')")
        assert cur.fetchone()[0] == "palazzo"


def test_garment_normalize_one_maps_known_aliases(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute("SELECT public.garment_normalize_one(%s)", ("plazo",))
        assert cur.fetchone()[0] == "palazzo"

        cur.execute("SELECT public.garment_normalize_one(%s)", ("  Cigarette Pant ",))
        assert cur.fetchone()[0] == "cigarette_pants"


def test_garment_normalize_one_keeps_and_logs_unknown(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute("SELECT public.garment_normalize_one(%s)", ("lehenga_skirt_xyz",))
        (normalized,) = cur.fetchone()
        assert normalized == "lehenga_skirt_xyz"

        cur.execute(
            "SELECT occurrences FROM garment_unknown_types WHERE slug = %s",
            ("lehenga_skirt_xyz",),
        )
        row = cur.fetchone()

    assert row is not None, "unknown garment slug was not captured"
    assert row[0] == 1


def test_garment_log_unknown_increments_on_repeat(db_conn: Any) -> None:
    probe_slug = f"probe_{uuid.uuid4().hex[:8]}"
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT public.garment_log_unknown(%s, 'test', NULL)", (probe_slug,)
        )
        cur.execute(
            "SELECT public.garment_log_unknown(%s, 'test', NULL)", (probe_slug,)
        )
        cur.execute(
            "SELECT occurrences FROM garment_unknown_types WHERE slug = %s", (probe_slug,)
        )
        rows = cur.fetchall()

    assert len(rows) == 1, "atomic upsert must never produce two rows for the same slug"
    assert rows[0][0] == 2


def test_garment_normalisation_functions_are_security_definer_with_pinned_search_path(
    db_conn: Any,
) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.proname, p.prosecdef, p.proconfig
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname LIKE 'garment_%%'
            """
        )
        rows = {name: (secdef, config) for name, secdef, config in cur.fetchall()}

    for name in (
        "garment_normalize_one",
        "garment_is_known",
        "garment_log_unknown",
    ):
        assert name in rows, f"{name} is missing"
        secdef, config = rows[name]
        assert secdef is True, f"{name} must be SECURITY DEFINER"
        assert config and any(c.startswith("search_path=") for c in config), (
            f"{name} must pin search_path"
        )

    # garment_normalize_shape touches no table -- NOT SECURITY DEFINER (design §3.3).
    assert "garment_normalize_shape" in rows
    shape_secdef, shape_config = rows["garment_normalize_shape"]
    assert shape_secdef is False
    assert shape_config and any(c.startswith("search_path=") for c in shape_config)


def test_garment_types_seed_covers_the_ten_sourced_ethnic_bottoms(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT key FROM garment_types WHERE key = ANY(%s) AND parent_key = 'ethnic_bottom'",
            (list(EXPECTED_TEN_SOURCED_ETHNIC_BOTTOMS),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == EXPECTED_TEN_SOURCED_ETHNIC_BOTTOMS


def test_no_kurti_row_exists(db_conn: Any) -> None:
    """B.1 finding #2: kurti is a length variant of kurta, not a sibling
    type. Asserted as a negative so a future ticket cannot silently
    reintroduce the mistake (design §7 edge case 7)."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM garment_types WHERE key = 'kurti'")
        row = cur.fetchone()

    assert row is None


def test_mekhela_and_mundu_two_piece_garments_are_not_full_body(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT key, slot, requires_with FROM garment_types WHERE key IN ('mekhela', 'mundu') "
            "ORDER BY key"
        )
        rows = {key: (slot, requires_with) for key, slot, requires_with in cur.fetchall()}

    assert set(rows) == {"mekhela", "mundu"}
    for key, (slot, _requires_with) in rows.items():
        assert slot == "legs", f"{key} must not be modelled as a single full_body type"
    assert rows["mekhela"][1] == ["sador"]
    assert rows["mundu"][1] == ["neriyathu"]


def test_saree_children_carry_the_correct_length_yards(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT key, styling_rules->>'length_yards' FROM garment_types "
            "WHERE key IN ('saree', 'nauvari', 'madisar')"
        )
        rows = dict(cur.fetchall())

    assert rows["saree"] == "6"
    assert rows["nauvari"] == "9"
    assert rows["madisar"] == "9"


def test_garment_set_components_resolve_to_seeded_types(db_conn: Any) -> None:
    """The FK already guarantees this; this test documents the intent (the
    next test is the free-text array case that has NO such guarantee)."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT set_key, component_key FROM garment_set_components")
        rows = cur.fetchall()
        cur.execute("SELECT key FROM garment_types")
        keys = {row[0] for row in cur.fetchall()}

    assert rows, "garment_set_components seed is empty"
    for set_key, component_key in rows:
        assert set_key in keys
        assert component_key in keys


def test_unseeded_requires_with_target_is_a_documented_gap_not_a_crash(db_conn: Any) -> None:
    """saree.requires_with contains 'petticoat', which has no row in
    garment_types -- a deliberate, documented gap (design §7 edge case 9),
    not an oversight. Assert the schema permits it by design: no CHECK/FK
    exists on requires_with's contents."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT requires_with FROM garment_types WHERE key = 'saree'")
        (requires_with,) = cur.fetchone()
        cur.execute("SELECT key FROM garment_types WHERE key = 'petticoat'")
        petticoat_row = cur.fetchone()

    assert requires_with is not None and "petticoat" in requires_with
    assert petticoat_row is None, "petticoat is deliberately unseeded"


def test_rls_enabled_on_all_four_garment_tables(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            """,
            (list(EXPECTED_GARMENT_TYPE_TABLES),),
        )
        rls_by_table = dict(cur.fetchall())

    assert set(rls_by_table) == EXPECTED_GARMENT_TYPE_TABLES
    disabled = [table for table, enabled in rls_by_table.items() if not enabled]
    assert not disabled, f"RLS not enabled on: {disabled}"


def test_only_select_policies_exist_on_garment_types_aliases_and_set_components(
    db_conn: Any,
) -> None:
    """Absence of a write policy IS the write-protection mechanism (design
    §3.4). A permissive INSERT/UPDATE/DELETE policy appearing here is a
    regression, not a fix. garment_unknown_types gets ZERO policies."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT tablename, cmd FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            (list(EXPECTED_GARMENT_TYPE_TABLES),),
        )
        policies = {(table, cmd) for table, cmd in cur.fetchall()}

    assert policies == {
        ("garment_types", "SELECT"),
        ("garment_type_aliases", "SELECT"),
        ("garment_set_components", "SELECT"),
    }


# test_authenticated_cannot_write_garment_types_but_service_role_can is
# deliberately NOT automated here -- design §6.3 scopes it to QA's manual/
# live verification (an authenticated-JWT INSERT denied, the same INSERT
# succeeding with the service_role key), the same posture as this module's
# other cross-role RLS checks that need two distinct real credentials
# rather than `SET ROLE` alone.


# ==========================================================================
# SS-035 -- Occasion-Aware Wear History (occasion_key + outfit_id, 015)
#
# Like the rest of this module, these are SKIPPED unless psycopg2 and
# SUPABASE_DB_URL are both available. Every write below is rolled back by
# the db_conn fixture, so none of them persists against the live project.
# ==========================================================================


# ==========================================================================


def _insert_wardrobe_item(cur: Any, user_id: str, purchase_price: int | None = None) -> str:
    item_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO wardrobe_items (id, user_id, image_url, category, purchase_price) "
        "VALUES (%s, %s, %s, 'western_top', %s)",
        (item_id, user_id, f"https://example.com/{uuid.uuid4()}.jpg", purchase_price),
    )
    return item_id


def _insert_outfit(cur: Any, user_id: str) -> str:
    outfit_id = str(uuid.uuid4())
    cur.execute("INSERT INTO outfits (id, user_id) VALUES (%s, %s)", (outfit_id, user_id))
    return outfit_id


def test_wear_occasion_key_and_outfit_id_columns_exist(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'wardrobe_item_wears'
              AND column_name IN ('occasion_key', 'outfit_id')
            """
        )
        rows = {row[0]: row for row in cur.fetchall()}

    assert set(rows) == {"occasion_key", "outfit_id"}
    assert rows["occasion_key"][1] == "YES"
    assert rows["occasion_key"][2] == "text"
    assert rows["outfit_id"][1] == "YES"
    assert rows["outfit_id"][2] == "uuid"


def test_server_version_is_at_least_15(db_conn: Any) -> None:
    """The gate this migration's own first statement asserts -- checked
    directly rather than assumed (design §3.1/§9 Q1)."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT current_setting('server_version_num')::int")
        (version_num,) = cur.fetchone()

    assert version_num >= 150000


def test_widened_unique_constraint_exists_and_is_nulls_not_distinct(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.indnullsnotdistinct
            FROM pg_constraint c
            JOIN pg_index i ON i.indexrelid = c.conindid
            WHERE c.conname = 'wardrobe_item_wears_one_per_day_per_occasion'
            """
        )
        row = cur.fetchone()

    assert row is not None, "wardrobe_item_wears_one_per_day_per_occasion constraint not found"
    assert row[0] is True, "NULLS NOT DISTINCT is load-bearing (BL-071) -- see design §3.3"


def test_old_one_per_day_constraint_no_longer_exists(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint WHERE conname = 'wardrobe_item_wears_one_per_day'"
        )
        row = cur.fetchone()

    assert row is None, "the narrowing constraint should have been replaced, not kept alongside"


def test_same_item_same_day_two_occasions_both_insert(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'office')",
            (item_id, owner),
        )
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'puja')",
            (item_id, owner),
        )
        cur.execute("SELECT count(*) FROM wardrobe_item_wears WHERE item_id = %s", (item_id,))
        (count,) = cur.fetchone()

    assert count == 2


def test_same_item_same_day_same_occasion_second_insert_is_rejected(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'office')",
            (item_id, owner),
        )

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'office')",
            (item_id, owner),
        )


def test_same_item_same_day_two_null_occasion_rows_are_rejected(db_conn: Any) -> None:
    """The BL-071 regression guard: without NULLS NOT DISTINCT, repeat
    one-tap "Mark Worn" taps (which write occasion_key=NULL) would each
    insert a new row and silently inflate wear_count."""
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
            "VALUES (%s, %s, CURRENT_DATE)",
            (item_id, owner),
        )

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
            "VALUES (%s, %s, CURRENT_DATE)",
            (item_id, owner),
        )


def test_wear_count_is_not_inflated_by_a_rejected_duplicate(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
            "VALUES (%s, %s, CURRENT_DATE)",
            (item_id, owner),
        )

        cur.execute("SAVEPOINT before_dupe")
        try:
            cur.execute(
                "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
                "VALUES (%s, %s, CURRENT_DATE)",
                (item_id, owner),
            )
        except psycopg2.errors.UniqueViolation:
            cur.execute("ROLLBACK TO SAVEPOINT before_dupe")

        cur.execute("SELECT wear_count FROM wardrobe_items WHERE id = %s", (item_id,))
        (wear_count,) = cur.fetchone()

    assert wear_count == 1


def test_alias_spelling_collapses_onto_the_canonical_key_before_uniqueness(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'work') RETURNING occasion_key",
            (item_id, owner),
        )
        (stored,) = cur.fetchone()
        assert stored == "office"

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'office')",
            (item_id, owner),
        )


def test_unknown_slug_is_stored_and_captured_not_dropped(db_conn: Any) -> None:
    probe_slug = f"probe_{uuid.uuid4().hex[:8]}"
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, %s) RETURNING occasion_key",
            (item_id, owner, probe_slug),
        )
        (stored,) = cur.fetchone()

        cur.execute(
            "SELECT occurrences, sample_source FROM occasion_unknown_tags WHERE slug = %s",
            (probe_slug,),
        )
        row = cur.fetchone()

    assert stored == probe_slug, "an unknown occasion must never be dropped"
    assert row is not None, "unknown slug was not captured"
    assert row[0] == 1
    assert row[1] == "wardrobe_item_wears"


def test_malformed_slug_is_normalised_not_rejected(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'Wedding Guest!!') RETURNING occasion_key",
            (item_id, owner),
        )
        (stored,) = cur.fetchone()

    assert stored == "wedding_guest"


def test_all_punctuation_slug_becomes_null(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, '!!!') RETURNING occasion_key",
            (item_id, owner),
        )
        (stored,) = cur.fetchone()

    assert stored is None


def test_occasion_key_shape_check_rejects_an_empty_string_written_by_service_role(
    db_conn: Any,
) -> None:
    """The normalisation trigger always turns '' into NULL before the CHECK
    ever sees it, so this disables the trigger to exercise the CHECK
    directly -- the backstop it is designed to be (design §3.4)."""
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "ALTER TABLE wardrobe_item_wears "
            "DISABLE TRIGGER trg_wardrobe_item_wears_normalize_occasion_key"
        )

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, '')",
            (item_id, owner),
        )


def test_deleting_an_outfit_nulls_outfit_id_and_leaves_the_wear_row(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        outfit_id = _insert_outfit(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, outfit_id) "
            "VALUES (%s, %s, CURRENT_DATE, %s) RETURNING id",
            (item_id, owner, outfit_id),
        )
        (wear_id,) = cur.fetchone()

        cur.execute("DELETE FROM outfits WHERE id = %s", (outfit_id,))

        cur.execute("SELECT outfit_id FROM wardrobe_item_wears WHERE id = %s", (wear_id,))
        (stored_outfit_id,) = cur.fetchone()

    assert stored_outfit_id is None, "the wear row must survive an outfit delete"


def test_deleting_an_outfit_does_not_change_wear_count_or_cost_per_wear(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner, purchase_price=1000)
        outfit_id = _insert_outfit(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, outfit_id) "
            "VALUES (%s, %s, CURRENT_DATE, %s)",
            (item_id, owner, outfit_id),
        )
        cur.execute(
            "SELECT wear_count, cost_per_wear FROM wardrobe_items WHERE id = %s", (item_id,)
        )
        before = cur.fetchone()

        cur.execute("DELETE FROM outfits WHERE id = %s", (outfit_id,))

        cur.execute(
            "SELECT wear_count, cost_per_wear FROM wardrobe_items WHERE id = %s", (item_id,)
        )
        after = cur.fetchone()

    assert before == after, "outfit deletion must never move wear_count/cost_per_wear"


def test_outfit_fk_rejects_an_outfit_belonging_to_another_user(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        other = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        other_outfit_id = _insert_outfit(cur, other)

    with db_conn.cursor() as cur, pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, outfit_id) "
            "VALUES (%s, %s, CURRENT_DATE, %s)",
            (item_id, owner, other_outfit_id),
        )


def test_wear_recency_reports_last_worn_overall_and_for_the_occasion_distinctly(
    db_conn: Any,
) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, '2026-07-20', 'office')",
            (item_id, owner),
        )
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, '2026-07-25', 'puja')",
            (item_id, owner),
        )

        cur.execute("SELECT * FROM public.wear_recency(%s, 'office')", (owner,))
        row = cur.fetchone()

    assert row is not None
    result_item_id, last_worn_on, last_worn_on_for_occasion, wears_for_occasion = row
    assert result_item_id == item_id
    assert str(last_worn_on) == "2026-07-25"
    assert str(last_worn_on_for_occasion) == "2026-07-20"
    assert wears_for_occasion == 1


def test_wear_recency_never_matches_a_null_occasion_row(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
            "VALUES (%s, %s, CURRENT_DATE)",
            (item_id, owner),
        )

        cur.execute("SELECT * FROM public.wear_recency(%s, 'office')", (owner,))
        row = cur.fetchone()

    assert row is not None
    _, _, last_worn_on_for_occasion, wears_for_occasion = row
    assert last_worn_on_for_occasion is None
    assert wears_for_occasion == 0


def test_wear_recency_with_a_null_occasion_argument_matches_nothing(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on, occasion_key) "
            "VALUES (%s, %s, CURRENT_DATE, 'office')",
            (item_id, owner),
        )

        cur.execute("SELECT * FROM public.wear_recency(%s, NULL)", (owner,))
        row = cur.fetchone()

    assert row is not None
    _, _, last_worn_on_for_occasion, wears_for_occasion = row
    assert last_worn_on_for_occasion is None
    assert wears_for_occasion == 0


def test_wear_recency_is_rls_scoped_and_not_security_definer(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        other = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
            "VALUES (%s, %s, CURRENT_DATE)",
            (item_id, owner),
        )

        cur.execute(
            """
            SELECT p.prosecdef
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = 'wear_recency'
            """
        )
        (prosecdef,) = cur.fetchone()

        cur.execute("SET ROLE authenticated")
        try:
            cur.execute(
                "SET request.jwt.claims = %s",
                (f'{{"sub": "{other}", "role": "authenticated"}}',),
            )
            # Explicitly pass the OWNER's id -- p_user_id is a filter IN
            # ADDITION to RLS, not instead of it (design §3.7). If RLS were
            # not in force, this would still (wrongly) return the owner's row.
            cur.execute("SELECT * FROM public.wear_recency(%s)", (owner,))
            rows_visible_to_other = cur.fetchall()
        finally:
            cur.execute("RESET ROLE")

    assert prosecdef is False, "wear_recency must be SECURITY INVOKER, not DEFINER"
    assert rows_visible_to_other == []


def test_normalisation_trigger_is_security_definer_with_a_pinned_search_path(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.prosecdef, p.proconfig
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = 'wear_occasion_key_normalize_trigger'
            """
        )
        row = cur.fetchone()

    assert row is not None, "wear_occasion_key_normalize_trigger is missing"
    secdef, config = row
    assert secdef is True
    assert config and any(c.startswith("search_path=") for c in config)


def test_new_indexes_exist_and_the_outfit_one_is_partial(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = ANY(%s)
            """,
            (["idx_item_wears_user_occasion_worn", "idx_item_wears_outfit_id"],),
        )
        rows = dict(cur.fetchall())

    assert set(rows) == {"idx_item_wears_user_occasion_worn", "idx_item_wears_outfit_id"}
    assert "where" in rows["idx_item_wears_outfit_id"].lower()


def test_outfits_id_user_id_unique_constraint_exists(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute("SELECT conname FROM pg_constraint WHERE conname = 'outfits_id_user_id_key'")
        row = cur.fetchone()

    assert row is not None, "outfits_id_user_id_key prerequisite for the composite FK is missing"


def test_new_columns_and_constraint_carry_comments(db_conn: Any) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname, col_description(a.attrelid, a.attnum)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'wardrobe_item_wears' AND a.attname IN ('occasion_key', 'outfit_id')
            """
        )
        col_comments = dict(cur.fetchall())

        cur.execute(
            "SELECT obj_description(oid) FROM pg_constraint "
            "WHERE conname = 'wardrobe_item_wears_one_per_day_per_occasion'"
        )
        row = cur.fetchone()
        constraint_comment = row[0] if row else None

    assert col_comments.get("occasion_key"), "occasion_key is missing its COMMENT"
    assert col_comments.get("outfit_id"), "outfit_id is missing its COMMENT"
    assert constraint_comment, "the widened constraint is missing its COMMENT"


def test_wear_stats_trigger_still_recomputes_after_the_widening(db_conn: Any) -> None:
    """008/006's trigger-maintained caches (wear_count/last_worn_at/
    cost_per_wear) must be unchanged in shape and behaviour under the
    widened constraint (AC #5, BL-004)."""
    with db_conn.cursor() as cur:
        owner = _insert_user(cur)
        item_id = _insert_wardrobe_item(cur, owner, purchase_price=1000)
        cur.execute(
            "INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on) "
            "VALUES (%s, %s, CURRENT_DATE) RETURNING id",
            (item_id, owner),
        )
        (wear_id,) = cur.fetchone()

        cur.execute(
            "SELECT wear_count, last_worn_at, cost_per_wear FROM wardrobe_items WHERE id = %s",
            (item_id,),
        )
        after_insert = cur.fetchone()

        cur.execute("DELETE FROM wardrobe_item_wears WHERE id = %s", (wear_id,))
        cur.execute(
            "SELECT wear_count, last_worn_at, cost_per_wear FROM wardrobe_items WHERE id = %s",
            (item_id,),
        )
        after_delete = cur.fetchone()

    assert after_insert[0] == 1
    assert after_insert[1] is not None
    assert after_insert[2] == 1000
    assert after_delete == (0, None, 1000)
