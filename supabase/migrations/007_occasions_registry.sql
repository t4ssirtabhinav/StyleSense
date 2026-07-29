-- ============================================================
-- SS-025 — Occasion Taxonomy & Extensibility Migration
-- STEP 1 of 3: EXPAND (purely additive — nothing reads these yet)
--
-- Per docs/tickets/SS-025-design.md §4. Forward-only: 001_initial.sql is
-- NEVER edited (BL-060 — the CI drift check has a false-positive history;
-- do not feed it).
--
-- This file creates the data-driven occasion registry that replaces the
-- 12-value `occasion_type` ENUM. Adding an occasion becomes an INSERT.
-- 008 switches the four columns to TEXT/TEXT[]; 009 drops the enum and the
-- superseded `occasion_types` onboarding table.
-- ============================================================

-- ------------------------------------------------------------
-- Tables
-- ------------------------------------------------------------

-- Null semantics (design §3.1) — these are the #1 silent-failure mode:
--   region_scope IS NULL  means UNIVERSAL / pan-India, NOT "no regions".
--   culture_scope IS NULL means the same.
-- The empty array is forbidden by CHECK precisely so nobody can write
-- "applies nowhere" and get an occasion that silently never matches.
-- Canonical applicability predicate, to be copied verbatim wherever
-- region/culture filtering happens:
--   (region_scope  IS NULL OR :user_region  = ANY(region_scope))
--   AND (culture_scope IS NULL OR :user_culture = ANY(culture_scope))
--
-- badge_color is a DESIGN-TOKEN KEY, not a hex (design §3.1). NativeWind
-- class names resolve at build time and CLAUDE.md forbids inline styles in
-- JSX, so an arbitrary DB hex cannot be rendered. Its value set IS Badge's
-- existing OccasionKey union (components/ui/Badge.tsx). NOT NULL + CHECK
-- means every occasion has a colour by construction — BL-008's patchy
-- 4-coloured/8-neutral rendering cannot recur no matter how many
-- occasions are added.
CREATE TABLE occasions (
  key            TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  parent_key     TEXT REFERENCES occasions(key) ON DELETE RESTRICT
                   CHECK (parent_key IS DISTINCT FROM key),
  label          TEXT NOT NULL,
  labels_i18n    JSONB NOT NULL DEFAULT '{}'::jsonb,
  kind           TEXT NOT NULL CHECK (kind IN (
                   'everyday', 'ceremony', 'festival', 'travel', 'sport',
                   'professional', 'social', 'milestone', 'religious')),
  formality      SMALLINT NOT NULL CHECK (formality BETWEEN 0 AND 10),
  region_scope   TEXT[] CHECK (region_scope  IS NULL OR cardinality(region_scope)  > 0),
  culture_scope  TEXT[] CHECK (culture_scope IS NULL OR cardinality(culture_scope) > 0),
  styling_rules  JSONB NOT NULL DEFAULT '{}'::jsonb,
  date_rule      JSONB,
  tier_gate      TEXT NOT NULL DEFAULT 'free'
                   CHECK (tier_gate IN ('free', 'premium', 'atelier')),
  badge_color    TEXT NOT NULL
                   CHECK (badge_color IN ('wedding', 'office', 'festival', 'casual')),
  is_active      BOOLEAN NOT NULL DEFAULT true,
  sort_order     INTEGER NOT NULL DEFAULT 100,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- No GIN on region_scope/culture_scope: the table is 12 rows and will be
-- low-hundreds at most; a sequential scan is correct here (design §3.1).
CREATE INDEX idx_occasions_active_sort ON occasions (is_active, sort_order);
CREATE INDEX idx_occasions_parent      ON occasions (parent_key);

-- `alias` and `occasions.key` must be disjoint. This is deliberately NOT
-- enforced by a constraint (Postgres has no cross-table CHECK) — it is
-- enforced by RESOLUTION ORDER (canonical key wins before alias lookup, so
-- a collision is inert) plus an explicit test. Do not add a trigger.
CREATE TABLE occasion_aliases (
  alias        TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  occasion_key TEXT NOT NULL REFERENCES occasions(key) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_occasion_aliases_key ON occasion_aliases (occasion_key);

-- The durable half of "store it and log it for review rather than dropping
-- the tag or failing the item write" (raw ticket's Edge Cases). A backend
-- logger.info would only cover the Gemini path; this covers EVERY writer,
-- including the outfit/social-post paths that do not exist yet.
CREATE TABLE occasion_unknown_tags (
  slug           TEXT PRIMARY KEY,
  occurrences    INTEGER NOT NULL DEFAULT 1,
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_source  TEXT,   -- 'wardrobe_items'|'outfits'|'suggestion_sessions'|'social_posts'
  sample_user_id UUID
);

-- ------------------------------------------------------------
-- RLS — mirrors 003_onboarding_taxonomies.sql's established pattern
--
-- DELIBERATELY no INSERT/UPDATE/DELETE policy on any of the three, and no
-- policy at all on occasion_unknown_tags. With RLS enabled and no matching
-- policy, writes from anon/authenticated are denied; service_role bypasses
-- RLS. ABSENCE OF A POLICY *IS* THE WRITE-PROTECTION MECHANISM — do not
-- "fix" this by adding a permissive write policy.
-- ------------------------------------------------------------
ALTER TABLE occasions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE occasion_aliases      ENABLE ROW LEVEL SECURITY;
ALTER TABLE occasion_unknown_tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_occasions" ON occasions
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_occasion_aliases" ON occasion_aliases
  FOR SELECT USING (auth.role() = 'authenticated');

-- ------------------------------------------------------------
-- Seed — the 12 existing enum keys, byte-identical to 001_initial.sql:18-21
--
-- sort_order reproduces the ENUM's declaration order (which is also
-- OCCASION_TYPES' order in wardrobe.constants.ts), so every shipped picker
-- renders in exactly the order it does today.
--   labels_i18n   -> '{}' for all 12 (BL-090: no approved translations exist)
--   styling_rules -> '{}' for all 12 (populating it is SS-027's job)
--   region_scope / culture_scope / date_rule -> NULL (universal)
--   tier_gate -> 'free', parent_key -> NULL, is_active -> true for all 12
--
-- label/kind/formality/badge_color are the Architect's call (nothing
-- upstream pins them). formality is an ordinal for SS-027's pre-filter and
-- is tunable later with an UPDATE, no migration.
-- ------------------------------------------------------------
INSERT INTO occasions (key, label, kind, formality, badge_color, sort_order) VALUES
  ('office',        'Office',        'professional', 6, 'office',    1),
  ('casual',        'Casual',        'everyday',     2, 'casual',    2),
  ('date_night',    'Date Night',    'social',       6, 'wedding',   3),
  ('wedding_guest', 'Wedding Guest', 'ceremony',     9, 'wedding',   4),
  ('festival',      'Festival',      'festival',     7, 'festival',  5),
  ('puja',          'Puja',          'religious',    6, 'festival',  6),
  ('party',         'Party',         'social',       7, 'festival',  7),
  ('travel',        'Travel',        'travel',       3, 'casual',    8),
  ('workout',       'Workout',       'sport',        1, 'casual',    9),
  ('beach',         'Beach',         'travel',       2, 'casual',   10),
  ('formal_event',  'Formal Event',  'ceremony',     8, 'wedding',  11),
  ('college',       'College',       'everyday',     3, 'casual',   12);

-- The first two rows are LOAD-BEARING DATA-MIGRATION MAPPINGS, not
-- conveniences: the shipped `occasion_types` onboarding table (003) and
-- OCCASION_PILLS (home.constants.ts) both use `wedding`/`date`, and live
-- user preference data does too. Without these, 009's backfill would blank
-- a user's saved onboarding priorities. The other six are plausible
-- Gemini/user variants; adding or removing them later is an INSERT/DELETE.
INSERT INTO occasion_aliases (alias, occasion_key) VALUES
  ('wedding',  'wedding_guest'),
  ('date',     'date_night'),
  ('work',     'office'),
  ('gym',      'workout'),
  ('pooja',    'puja'),
  ('vacation', 'travel'),
  ('formal',   'formal_event'),
  ('everyday', 'casual');

-- ------------------------------------------------------------
-- Normalisation + logging functions (design §3.6)
--
-- Contract, identical in SQL, Python and TypeScript:
--   1. trim -> lower -> collapse runs of whitespace and '-' to a single
--      '_' -> strip any character outside [a-z0-9_]
--   2. if the result matches occasions.key             -> use it
--   3. else if it matches occasion_aliases.alias       -> use occasion_key
--   4. else -> KEEP the normalised string as-is and record it in
--      occasion_unknown_tags. Never drop it. Never fail the write.
-- Then dedupe PRESERVING FIRST-OCCURRENCE ORDER. Never sort.
--
-- Step 2 before step 3 is what makes an alias/key collision inert.
--
-- All are SECURITY DEFINER with SET search_path = public, pg_temp, so
-- normalisation never depends on the caller's role or RLS visibility and
-- the unknown-tag log is writable from a trigger without granting anyone
-- table access. These are privileged objects: they take only text/uuid
-- arguments, execute no dynamic SQL, and write exactly one table. KEEP
-- THEM THAT WAY.
-- ------------------------------------------------------------

-- Shape-only normalisation (step 1). Not SECURITY DEFINER — it touches no
-- table at all, so it needs no elevated rights.
CREATE OR REPLACE FUNCTION public.occasion_normalize_shape(p_raw TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
  SELECT NULLIF(
    regexp_replace(
      regexp_replace(lower(btrim(p_raw)), '[[:space:]-]+', '_', 'g'),
      '[^a-z0-9_]', '', 'g'
    ),
    ''
  );
$$;

COMMENT ON FUNCTION public.occasion_normalize_shape(TEXT) IS
  'SS-025 step 1 of the occasion normalisation contract: trim/lower/collapse to underscore/strip. Returns NULL for NULL or an all-punctuation input.';

CREATE OR REPLACE FUNCTION public.occasion_normalize_one(p_raw TEXT)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_shaped TEXT;
  v_mapped TEXT;
BEGIN
  IF p_raw IS NULL THEN
    RETURN NULL;
  END IF;

  v_shaped := public.occasion_normalize_shape(p_raw);
  IF v_shaped IS NULL THEN
    RETURN NULL;
  END IF;

  -- Step 2 — canonical key wins FIRST. This ordering is what makes an
  -- alias/key collision inert (design §3.3).
  IF EXISTS (SELECT 1 FROM public.occasions o WHERE o.key = v_shaped) THEN
    RETURN v_shaped;
  END IF;

  -- Step 3 — alias lookup.
  SELECT a.occasion_key INTO v_mapped
  FROM public.occasion_aliases a
  WHERE a.alias = v_shaped;

  IF v_mapped IS NOT NULL THEN
    RETURN v_mapped;
  END IF;

  -- Step 4 — unknown: keep the normalised string. Never drop it.
  RETURN v_shaped;
END;
$$;

CREATE OR REPLACE FUNCTION public.occasion_is_known(p_slug TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT EXISTS (SELECT 1 FROM public.occasions o WHERE o.key = p_slug);
$$;

CREATE OR REPLACE FUNCTION public.occasion_log_unknown(
  p_slug TEXT,
  p_src  TEXT,
  p_uid  UUID
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_slug IS NULL THEN
    RETURN;
  END IF;
  -- Single atomic INSERT ... ON CONFLICT DO UPDATE — deliberately NOT a
  -- read-then-write (BL-066/BL-036: this ticket adds no third instance of
  -- that bug class).
  INSERT INTO public.occasion_unknown_tags (slug, sample_source, sample_user_id)
  VALUES (p_slug, p_src, p_uid)
  ON CONFLICT (slug) DO UPDATE
    SET occurrences  = occasion_unknown_tags.occurrences + 1,
        last_seen_at = now();
END;
$$;

CREATE OR REPLACE FUNCTION public.occasion_normalize_array(
  p_raw TEXT[],
  p_src TEXT,
  p_uid UUID
)
RETURNS TEXT[]
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_result TEXT[] := '{}';
  v_item   TEXT;
  v_norm   TEXT;
BEGIN
  IF p_raw IS NULL THEN
    RETURN NULL;
  END IF;

  FOREACH v_item IN ARRAY p_raw LOOP
    v_norm := public.occasion_normalize_one(v_item);
    IF v_norm IS NULL THEN
      CONTINUE;
    END IF;
    -- Dedupe preserving FIRST-occurrence order. Never sort — order is not
    -- semantic for occasion_tags, but preserving it keeps the migration
    -- fixture's byte-identical assertion trivially true.
    IF NOT (v_norm = ANY (v_result)) THEN
      v_result := array_append(v_result, v_norm);
      IF NOT public.occasion_is_known(v_norm) THEN
        PERFORM public.occasion_log_unknown(v_norm, p_src, p_uid);
      END IF;
    END IF;
  END LOOP;

  RETURN v_result;
END;
$$;

-- ============================================================
-- ROLLBACK: revert 007 (safe while nothing reads these — 008 has not run)
--
--   DROP FUNCTION IF EXISTS public.occasion_normalize_array(TEXT[], TEXT, UUID);
--   DROP FUNCTION IF EXISTS public.occasion_log_unknown(TEXT, TEXT, UUID);
--   DROP FUNCTION IF EXISTS public.occasion_is_known(TEXT);
--   DROP FUNCTION IF EXISTS public.occasion_normalize_one(TEXT);
--   DROP FUNCTION IF EXISTS public.occasion_normalize_shape(TEXT);
--   DROP TABLE IF EXISTS public.occasion_unknown_tags;
--   DROP TABLE IF EXISTS public.occasion_aliases;
--   DROP TABLE IF EXISTS public.occasions;
-- ============================================================
