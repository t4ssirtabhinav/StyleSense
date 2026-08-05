-- ============================================================
-- SS-036 — Pattern & Fabric Registries (resolves BL-079's pattern/fabric
-- half; colour stays open under BL-064)
--
-- Per docs/tickets/SS-036-design.md. Structurally lifted from
-- 007_occasions_registry.sql / 014_garment_types_registry.sql, with ONE
-- material difference: this ticket wires a row TRIGGER onto wardrobe_items
-- (the live write path for SS-012's tagging call, every mobile tag edit,
-- the upload-review save, and -- the least obvious one -- every "Mark Worn"
-- tap via 006's sync_wardrobe_item_wear_stats() UPDATE). See design §2 for
-- the full blast-radius table. Risk: high.
--
-- The one non-negotiable property, above every other AC: an
-- out-of-vocabulary pattern/fabric string must never fail an otherwise-good
-- write to wardrobe_items. Everything below exists to make that
-- structurally true (resolve-into-locals-then-assign, EXCEPTION WHEN
-- OTHERS, no FK from wardrobe_items to these registries, is_active
-- excluded from resolution) and provable (backend/tests/test_db_schema.py's
-- SS-036 section, esp. #29/#30) rather than merely asserted.
--
-- Ordering in this file is LOAD-BEARING: tables -> seed -> functions ->
-- backfill -> CREATE TRIGGER. Triggers are created LAST so the backfill's
-- own UPDATE does not re-enter them and cannot double-count captures.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Tables (design §3.1)
-- ------------------------------------------------------------

CREATE TABLE patterns (
  key         TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  label       TEXT NOT NULL,
  labels_i18n JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active   BOOLEAN NOT NULL DEFAULT true,
  sort_order  INTEGER NOT NULL DEFAULT 100,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Engine v2 fabric x weather attributes (design §3.6 -- decided, not
-- deferred, this ticket). NULL season_affinity means UNIVERSAL / no
-- seasonal opinion, exactly as region_scope IS NULL means pan-India in
-- 007/014 -- never "no seasons". 'all' is deliberately EXCLUDED from the
-- CHECK's value set so there is exactly one way to express "every season"
-- (NULL); permitting both would recreate the null-vs-empty silent-failure
-- mode 007's comments guard against. Note wardrobe_items.season_tags DOES
-- use 'all' -- a different column with a different (shipped, unchanged)
-- vocabulary; do not "harmonise" them.
-- `patterns` deliberately gets NO attribute columns -- asymmetric with
-- `fabrics` on purpose; see design §9 open question 3 / BL-126.
CREATE TABLE fabrics (
  key             TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  label           TEXT NOT NULL,
  labels_i18n     JSONB NOT NULL DEFAULT '{}'::jsonb,
  weight          TEXT     CHECK (weight IS NULL OR weight IN ('light','medium','heavy')),
  breathability   SMALLINT CHECK (breathability IS NULL OR breathability BETWEEN 0 AND 10),
  season_affinity TEXT[]   CHECK (
                    season_affinity IS NULL
                    OR (cardinality(season_affinity) > 0
                        AND season_affinity <@ ARRAY['summer','winter','monsoon'])),
  is_active       BOOLEAN NOT NULL DEFAULT true,
  sort_order      INTEGER NOT NULL DEFAULT 100,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_patterns_active_sort ON patterns (is_active, sort_order);
CREATE INDEX idx_fabrics_active_sort  ON fabrics  (is_active, sort_order);

-- `alias` and `patterns.key`/`fabrics.key` must be disjoint. Deliberately
-- NOT enforced by a constraint (Postgres has no cross-table CHECK) --
-- enforced by RESOLUTION ORDER (canonical key wins before alias lookup, so
-- a collision is inert) plus an explicit test. Do not add a trigger.
CREATE TABLE pattern_aliases (
  alias       TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  pattern_key TEXT NOT NULL REFERENCES patterns(key) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE fabric_aliases (
  alias      TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  fabric_key TEXT NOT NULL REFERENCES fabrics(key) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pattern_aliases_key ON pattern_aliases (pattern_key);
CREATE INDEX idx_fabric_aliases_key  ON fabric_aliases  (fabric_key);

-- The AC's "shared *_unknown_tags capture table", read literally: ONE table
-- serving both registries, discriminated by `attribute`. Shared rather than
-- two tables (unlike 007's occasion_unknown_tags / 014's
-- garment_unknown_types, each single-purpose) so the eventual colour
-- registry (BL-064's open half) widens a CHECK instead of adding a third
-- capture table. Name deliberately avoids colliding with 014's
-- garment_unknown_types (design §7 edge case 6).
CREATE TABLE attribute_unknown_tags (
  attribute      TEXT NOT NULL CHECK (attribute IN ('pattern','fabric')),
  slug           TEXT NOT NULL,
  occurrences    INTEGER NOT NULL DEFAULT 1,
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_source  TEXT,   -- 'wardrobe_items' | future writers, per 007's precedent
  sample_user_id UUID,   -- no FK, deliberately: a deleted user must not break capture
  PRIMARY KEY (attribute, slug)
);

-- No foreign key from wardrobe_items.pattern/.fabric to these registries,
-- EVER. An FK would turn an out-of-vocabulary Gemini string into a failed
-- tagging write -- the exact outcome the AC forbids. Asserted by test
-- (§6.1 #27), not just stated here.

-- ------------------------------------------------------------
-- RLS -- mirrors 007/014's established pattern
--
-- DELIBERATELY no INSERT/UPDATE/DELETE policy on any table, and no policy
-- at all on attribute_unknown_tags. With RLS enabled and no matching
-- policy, writes from anon/authenticated are denied; service_role bypasses
-- RLS. ABSENCE OF A POLICY *IS* THE WRITE-PROTECTION MECHANISM -- do not
-- "fix" this by adding a permissive write policy.
-- ------------------------------------------------------------
ALTER TABLE patterns               ENABLE ROW LEVEL SECURITY;
ALTER TABLE fabrics                ENABLE ROW LEVEL SECURITY;
ALTER TABLE pattern_aliases        ENABLE ROW LEVEL SECURITY;
ALTER TABLE fabric_aliases         ENABLE ROW LEVEL SECURITY;
ALTER TABLE attribute_unknown_tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_patterns" ON patterns
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_fabrics" ON fabrics
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_pattern_aliases" ON pattern_aliases
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_fabric_aliases" ON fabric_aliases
  FOR SELECT USING (auth.role() = 'authenticated');

-- ------------------------------------------------------------
-- 2. Seed -- transcribed VERBATIM from BL-064 (design §3.2), order
--    preserved. sort_order reproduces gemini_vision_adapter.py:104-109's
--    order. labels_i18n -> '{}' for every row (BL-090: no approved
--    translations exist -- same root cause as 007/014, not a new gap).
--    No new vocabulary invented.
-- ------------------------------------------------------------

INSERT INTO patterns (key, label, sort_order) VALUES
  ('solid',       'Solid',       10),
  ('stripes',     'Stripes',     20),
  ('checks',      'Checks',      30),
  ('floral',      'Floral',      40),
  ('block_print', 'Block Print', 50),
  ('bandhani',    'Bandhani',    60),
  ('ikat',        'Ikat',        70),
  ('paisley',     'Paisley',     80),
  ('polka_dots',  'Polka Dots',  90),
  ('embroidered', 'Embroidered', 100),
  ('printed',     'Printed',     110);

-- Fabric attribute values are Architect judgment (design §3.6, BL-125),
-- same class as occasions.formality / garment_types.base_formality --
-- flagged for stylist review before any Engine v2 scoring code consumes
-- them. `silk` and `khadi` carry NULL season_affinity ON PURPOSE: silk is
-- occasion-driven rather than season-driven in Indian wear, and khadi's
-- whole point is that it is cool in summer and warm in winter.
INSERT INTO fabrics (key, label, sort_order, weight, breathability, season_affinity) VALUES
  ('cotton',     'Cotton',     10, 'light',  9, ARRAY['summer']),
  ('silk',       'Silk',       20, 'medium', 5, NULL),
  ('linen',      'Linen',      30, 'light',  10, ARRAY['summer']),
  ('denim',      'Denim',      40, 'heavy',  2, ARRAY['winter']),
  ('wool',       'Wool',       50, 'heavy',  1, ARRAY['winter']),
  ('rayon',      'Rayon',      60, 'light',  6, ARRAY['summer']),
  ('polyester',  'Polyester',  70, 'light',  2, ARRAY['monsoon']),
  ('georgette',  'Georgette',  80, 'light',  5, ARRAY['summer','monsoon']),
  ('chiffon',    'Chiffon',    90, 'light',  5, ARRAY['summer']),
  ('khadi',      'Khadi',      100, 'light', 9, NULL),
  ('chikankari', 'Chikankari', 110, 'light', 8, ARRAY['summer']);

-- ------------------------------------------------------------
-- 3. Alias seed -- representative, not exhaustive (007/014's stated
--    posture, design §3.3). Every alias already satisfies the
--    ^[a-z][a-z0-9_]*$ CHECK and is disjoint from the canonical key set
--    (asserted by test, not by constraint). Anything a hyphen/space/case
--    fold already resolves needs NO alias row.
-- ------------------------------------------------------------

INSERT INTO pattern_aliases (alias, pattern_key) VALUES
  ('plain','solid'), ('solids','solid'),
  ('striped','stripes'), ('stripe','stripes'),
  ('check','checks'), ('checked','checks'), ('checkered','checks'),
  ('chequered','checks'), ('plaid','checks'),
  ('florals','floral'), ('flowery','floral'),
  ('blockprint','block_print'), ('block_printed','block_print'),
  ('bandhej','bandhani'), ('bandhni','bandhani'),      -- bandhej: Gujarati/Rajasthani term
  ('ikkat','ikat'),
  ('paisleys','paisley'), ('ambi','paisley'),          -- ambi/keri: the Indian name
  ('polka_dot','polka_dots'), ('polkadots','polka_dots'),
  ('dots','polka_dots'), ('dotted','polka_dots'),
  ('embroidery','embroidered'),
  ('print','printed'), ('prints','printed'), ('digital_print','printed');

INSERT INTO fabric_aliases (alias, fabric_key) VALUES
  ('cottons','cotton'), ('pure_cotton','cotton'),
  ('silks','silk'), ('pure_silk','silk'), ('raw_silk','silk'),
  ('tussar_silk','silk'), ('banarasi_silk','silk'),    -- the ticket's own "tussar silk" example
  ('linens','linen'),
  ('jeans','denim'),
  ('woollen','wool'), ('woolen','wool'),
  ('viscose','rayon'), ('modal','rayon'), ('art_silk','rayon'),  -- art silk == artificial silk
  ('poly','polyester'), ('polyster','polyester'),
  ('georgett','georgette'),
  ('chifon','chiffon'),
  ('khaddar','khadi'),
  ('chikan','chikankari'), ('lucknowi','chikankari');

-- ------------------------------------------------------------
-- 4. Normalisation + logging functions (design §3.4)
--
-- Contract, identical in spirit to 007/014's:
--   1. trim -> lower -> collapse runs of whitespace and '-' to a single
--      '_' -> strip any character outside [a-z0-9_]
--   2. if the result matches patterns.key / fabrics.key -> use it
--   3. else if it matches pattern_aliases.alias / fabric_aliases.alias
--      -> use the mapped key
--   4. else -> KEEP the normalised string as-is. Never drop it. Never
--      fail the write.
-- Step 2 before step 3 is what makes an alias/key collision inert.
--
-- WHO LOGS AN UNKNOWN -- ONE PLACE, NO AMBIGUITY. pattern_normalize_one /
-- fabric_normalize_one RESOLVE ONLY; they never write. attribute_log_unknown
-- is invoked from exactly one caller: the trigger function below, which
-- after resolving checks NOT *_is_known(...) and logs with real context
-- (TG_TABLE_NAME, NEW.user_id). This deliberately differs from 014's
-- garment_normalize_one, which logs from inside itself with NULL/NULL
-- context because it had no call site to get context from (see BL-123).
-- CONSEQUENCE: any future non-trigger caller of *_normalize_one must call
-- attribute_log_unknown itself, or its unknowns go uncaptured. That is the
-- trade for keeping the resolver pure -- which is also what makes it safe
-- to call TWICE (e.g. inside the backfill's WHERE and SET clauses below)
-- without double-counting.
--
-- VOLATILE, NOT STABLE -- a deliberate correction of SS-034's precedent
-- (BL-123). garment_normalize_one (014) is declared STABLE while its
-- step-4 branch PERFORMs a write; Postgres documents modifying the
-- database from a STABLE/IMMUTABLE function as unwise/undefined
-- [trained-knowledge, not re-verified this pass]. Here *_normalize_one is
-- pure and could honestly be STABLE -- it is nevertheless declared VOLATILE
-- so a future edit adding a write inside it cannot silently inherit a
-- wrong label on a live write path. Asserted by test (§6.1 #16).
--
-- BOTH *_is_known AND THE RESOLUTION STEP IGNORE is_active. Resolution
-- matches on key existence only. If resolution filtered on is_active,
-- deactivating a registry row would instantly reclassify every existing
-- item value holding that key as "unknown" and start capturing it --
-- precisely the orphan/rewrite raw ticket edge case 5 forbids. is_active is
-- a PICK-LIST / DISPLAY FLAG ONLY. This is the single most likely thing for
-- a future contributor to "fix" wrongly -- don't. Asserted by test (§6.1 #30).
--
-- All SECURITY DEFINER (except the shape-only step, which touches no
-- table) with SET search_path = public, pg_temp.
-- ------------------------------------------------------------

-- Shape-only normalisation (step 1), shared by both attributes -- one
-- function rather than two identical copies (design §3.4). Not SECURITY
-- DEFINER: it touches no table, so it needs no elevated rights.
CREATE OR REPLACE FUNCTION public.attribute_normalize_shape(p_raw TEXT)
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

COMMENT ON FUNCTION public.attribute_normalize_shape(TEXT) IS
  'SS-036 step 1 of the pattern/fabric normalisation contract: trim/lower/collapse to underscore/strip. Returns NULL for NULL or an all-punctuation input. Shared by both attributes.';

CREATE OR REPLACE FUNCTION public.attribute_log_unknown(
  p_attribute TEXT,
  p_slug      TEXT,
  p_src       TEXT,
  p_uid       UUID
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
  -- Single atomic INSERT ... ON CONFLICT DO UPDATE -- deliberately NOT a
  -- read-then-write (BL-066/BL-036: this ticket adds no third instance of
  -- that bug class).
  INSERT INTO public.attribute_unknown_tags (attribute, slug, sample_source, sample_user_id)
  VALUES (p_attribute, p_slug, p_src, p_uid)
  ON CONFLICT (attribute, slug) DO UPDATE
    SET occurrences  = attribute_unknown_tags.occurrences + 1,
        last_seen_at = now();
END;
$$;

CREATE OR REPLACE FUNCTION public.pattern_is_known(p_slug TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  -- Deliberately ignores is_active -- see the module comment above.
  SELECT EXISTS (SELECT 1 FROM public.patterns p WHERE p.key = p_slug);
$$;

CREATE OR REPLACE FUNCTION public.fabric_is_known(p_slug TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  -- Deliberately ignores is_active -- see the module comment above.
  SELECT EXISTS (SELECT 1 FROM public.fabrics f WHERE f.key = p_slug);
$$;

-- VOLATILE (not STABLE -- see the module comment / BL-123). Pure resolver:
-- never writes, never logs. Deliberately ignores is_active (see above).
CREATE OR REPLACE FUNCTION public.pattern_normalize_one(p_raw TEXT)
RETURNS TEXT
LANGUAGE plpgsql
VOLATILE
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

  v_shaped := public.attribute_normalize_shape(p_raw);
  IF v_shaped IS NULL THEN
    RETURN NULL;
  END IF;

  -- Step 2 -- canonical key wins FIRST. This ordering is what makes an
  -- alias/key collision inert (design §3.4).
  IF EXISTS (SELECT 1 FROM public.patterns p WHERE p.key = v_shaped) THEN
    RETURN v_shaped;
  END IF;

  -- Step 3 -- alias lookup.
  SELECT a.pattern_key INTO v_mapped
  FROM public.pattern_aliases a
  WHERE a.alias = v_shaped;

  IF v_mapped IS NOT NULL THEN
    RETURN v_mapped;
  END IF;

  -- Step 4 -- unknown: keep the normalised string. Never drop it. Never
  -- log here -- the trigger is the only logger (see module comment).
  RETURN v_shaped;
END;
$$;

-- VOLATILE (not STABLE -- see the module comment / BL-123). Pure resolver:
-- never writes, never logs. Deliberately ignores is_active (see above).
CREATE OR REPLACE FUNCTION public.fabric_normalize_one(p_raw TEXT)
RETURNS TEXT
LANGUAGE plpgsql
VOLATILE
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

  v_shaped := public.attribute_normalize_shape(p_raw);
  IF v_shaped IS NULL THEN
    RETURN NULL;
  END IF;

  -- Step 2 -- canonical key wins FIRST. This ordering is what makes an
  -- alias/key collision inert (design §3.4).
  IF EXISTS (SELECT 1 FROM public.fabrics f WHERE f.key = v_shaped) THEN
    RETURN v_shaped;
  END IF;

  -- Step 3 -- alias lookup.
  SELECT a.fabric_key INTO v_mapped
  FROM public.fabric_aliases a
  WHERE a.alias = v_shaped;

  IF v_mapped IS NOT NULL THEN
    RETURN v_mapped;
  END IF;

  -- Step 4 -- unknown: keep the normalised string. Never drop it. Never
  -- log here -- the trigger is the only logger (see module comment).
  RETURN v_shaped;
END;
$$;

-- ------------------------------------------------------------
-- 5. One-time backfill of existing wardrobe_items rows (design §3.5)
--
-- Ordering in this file matters: tables -> seed -> functions -> backfill ->
-- CREATE TRIGGER (below). Creating the triggers LAST means this backfill's
-- own UPDATE does not re-enter them and cannot double-count captures.
--
-- Two passes: CAPTURE (every distinct non-null value that resolves to
-- neither a key nor an alias gets an attribute_unknown_tags row) then
-- REWRITE (only where normalisation actually changes the value). Capture
-- MUST be its own pass -- a value already in canonical shape (e.g.
-- 'tussar_silk' typed lowercase, which resolves via alias) is untouched by
-- the rewrite pass's WHERE clause, so it would be silently uncaptured if
-- capture were folded into the rewrite.
--
-- Calling *_normalize_one twice per row (once implicitly via the capture
-- pass, once in the rewrite's WHERE and SET) is safe precisely because the
-- resolvers above are pure -- no double-counted captures.
-- ------------------------------------------------------------

DO $$
DECLARE
  v_captured   INT := 0;
  v_normalised INT := 0;
  v_rec        RECORD;
  v_norm       TEXT;
BEGIN
  -- Pass 1: CAPTURE. MIN() has no UUID overload in Postgres, so the
  -- sample user_id is taken via a text-cast MIN (arbitrary-but-stable
  -- choice among matching rows -- "one sample user_id", not a specific one).
  FOR v_rec IN
    SELECT DISTINCT pattern AS raw_value, MIN(user_id::text)::uuid AS sample_user_id
    FROM wardrobe_items
    WHERE pattern IS NOT NULL
    GROUP BY pattern
  LOOP
    v_norm := public.pattern_normalize_one(v_rec.raw_value);
    IF v_norm IS NOT NULL AND NOT public.pattern_is_known(v_norm) THEN
      PERFORM public.attribute_log_unknown('pattern', v_norm, 'wardrobe_items', v_rec.sample_user_id);
      v_captured := v_captured + 1;
    END IF;
  END LOOP;

  FOR v_rec IN
    SELECT DISTINCT fabric AS raw_value, MIN(user_id::text)::uuid AS sample_user_id
    FROM wardrobe_items
    WHERE fabric IS NOT NULL
    GROUP BY fabric
  LOOP
    v_norm := public.fabric_normalize_one(v_rec.raw_value);
    IF v_norm IS NOT NULL AND NOT public.fabric_is_known(v_norm) THEN
      PERFORM public.attribute_log_unknown('fabric', v_norm, 'wardrobe_items', v_rec.sample_user_id);
      v_captured := v_captured + 1;
    END IF;
  END LOOP;

  -- Pass 2: REWRITE, only where normalisation actually changes the value.
  -- Keeps the backfill from touching rows that need nothing: no
  -- unnecessary row churn on the live project, and no unnecessary firing
  -- of trg_wardrobe_items_normalize_occasions (which would otherwise
  -- re-run occasion normalisation across the whole table).
  UPDATE wardrobe_items
     SET pattern = public.pattern_normalize_one(pattern),
         fabric  = public.fabric_normalize_one(fabric)
   WHERE (pattern IS NOT NULL AND pattern IS DISTINCT FROM public.pattern_normalize_one(pattern))
      OR (fabric  IS NOT NULL AND fabric  IS DISTINCT FROM public.fabric_normalize_one(fabric));
  GET DIAGNOSTICS v_normalised = ROW_COUNT;

  RAISE NOTICE 'SS-036 backfill: % rows rewritten, % distinct unknown values captured',
               v_normalised, v_captured;
END $$;

-- ------------------------------------------------------------
-- 6. Trigger function + triggers (design §3.4) -- created LAST, after the
--    backfill, so the backfill's own UPDATE above does not re-enter them.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.wardrobe_items_normalize_pattern_fabric_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_pattern TEXT;
  v_fabric  TEXT;
BEGIN
  -- Fast exit: nothing to do.
  IF NEW.pattern IS NULL AND NEW.fabric IS NULL THEN
    RETURN NEW;
  END IF;

  -- Resolve into LOCAL VARIABLES FIRST, assign to NEW.* only after both
  -- calls have returned. This guarantees the EXCEPTION handler below
  -- leaves NEW exactly as the caller wrote it, rather than half-rewritten.
  v_pattern := public.pattern_normalize_one(NEW.pattern);
  v_fabric  := public.fabric_normalize_one(NEW.fabric);

  NEW.pattern := v_pattern;
  NEW.fabric  := v_fabric;

  -- The trigger is the ONE place that logs an unknown (module comment
  -- above) -- it has real context (TG_TABLE_NAME, NEW.user_id) that the
  -- pure resolvers deliberately do not.
  IF v_pattern IS NOT NULL AND NOT public.pattern_is_known(v_pattern) THEN
    PERFORM public.attribute_log_unknown('pattern', v_pattern, TG_TABLE_NAME, NEW.user_id);
  END IF;
  IF v_fabric IS NOT NULL AND NOT public.fabric_is_known(v_fabric) THEN
    PERFORM public.attribute_log_unknown('fabric', v_fabric, TG_TABLE_NAME, NEW.user_id);
  END IF;

  RETURN NEW;

EXCEPTION WHEN OTHERS THEN
  -- THE structural guarantee behind the AC "an out-of-vocabulary fabric
  -- string still cannot fail an otherwise-good tagging result": whatever
  -- goes wrong inside normalisation (missing capture table, permission
  -- change, a future CHECK someone adds), the item write proceeds with the
  -- caller's ORIGINAL values (NEW was never touched on this path, since we
  -- resolved into locals first) and a server-log warning. WHEN OTHERS does
  -- not trap query_canceled/assert_failure [trained-knowledge], which is
  -- the desired behaviour -- a cancelled statement should stay cancelled.
  -- NOTE: the handler rolls back the implicit subtransaction, so a
  -- capture-row write is lost on the failure path; the item write
  -- surviving is the correct trade. Proven empirically, not just by
  -- inspection, by test #29 (renames attribute_unknown_tags mid-transaction
  -- and asserts the item insert still succeeds).
  RAISE WARNING 'SS-036 pattern/fabric normalisation skipped: %', SQLERRM;
  RETURN NEW;
END;
$$;

-- TWO triggers, not one, so the hot path is filtered DECLARATIVELY. A
-- single BEFORE INSERT OR UPDATE trigger (008's shape) cannot carry the
-- WHEN clause below, because the expression would reference OLD on the
-- INSERT path. The split is what keeps sync_wardrobe_item_wear_stats()'s
-- UPDATE wardrobe_items SET wear_count ... (design §2, fires on every Mark
-- Worn tap) from re-entering plpgsql at all -- and, more importantly, from
-- re-incrementing attribute_unknown_tags.occurrences for an item that
-- merely holds an unknown fabric. 008's occasion trigger has no such filter
-- and DOES re-run on every unrelated UPDATE; that is a real (low-severity)
-- defect in the shipped occasion capture counts, logged as BL-124 rather
-- than fixed here.
--
-- Both trigger names sort after trg_wardrobe_items_normalize_occasions, so
-- the occasion trigger fires first. The two touch disjoint columns, so
-- ordering is irrelevant -- asserted by test (§6.1 #24), not assumed.
CREATE TRIGGER trg_wardrobe_items_normalize_pattern_fabric_ins
  BEFORE INSERT ON wardrobe_items
  FOR EACH ROW EXECUTE FUNCTION public.wardrobe_items_normalize_pattern_fabric_trigger();

CREATE TRIGGER trg_wardrobe_items_normalize_pattern_fabric_upd
  BEFORE UPDATE ON wardrobe_items
  FOR EACH ROW
  WHEN (NEW.pattern IS DISTINCT FROM OLD.pattern
        OR NEW.fabric IS DISTINCT FROM OLD.fabric)
  EXECUTE FUNCTION public.wardrobe_items_normalize_pattern_fabric_trigger();

-- ============================================================
-- ROLLBACK: revert 016
--
-- The backfill's value REWRITE (section 5 above) is NOT reversible from
-- this block -- it cannot restore a pre-normalisation pattern/fabric
-- string. That is why design §5 step 2's before-fixture is mandatory and
-- must land in docs/worklog/SS-036.md BEFORE `supabase db push`, not after.
--
--   DROP TRIGGER IF EXISTS trg_wardrobe_items_normalize_pattern_fabric_upd ON wardrobe_items;
--   DROP TRIGGER IF EXISTS trg_wardrobe_items_normalize_pattern_fabric_ins ON wardrobe_items;
--   DROP FUNCTION IF EXISTS public.wardrobe_items_normalize_pattern_fabric_trigger();
--   DROP FUNCTION IF EXISTS public.fabric_normalize_one(TEXT);
--   DROP FUNCTION IF EXISTS public.pattern_normalize_one(TEXT);
--   DROP FUNCTION IF EXISTS public.fabric_is_known(TEXT);
--   DROP FUNCTION IF EXISTS public.pattern_is_known(TEXT);
--   DROP FUNCTION IF EXISTS public.attribute_log_unknown(TEXT, TEXT, TEXT, UUID);
--   DROP FUNCTION IF EXISTS public.attribute_normalize_shape(TEXT);
--   DROP TABLE IF EXISTS public.attribute_unknown_tags;
--   DROP TABLE IF EXISTS public.fabric_aliases;
--   DROP TABLE IF EXISTS public.pattern_aliases;
--   DROP TABLE IF EXISTS public.fabrics;
--   DROP TABLE IF EXISTS public.patterns;
-- ============================================================
