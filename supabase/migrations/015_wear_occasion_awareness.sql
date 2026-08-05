-- ============================================================
-- SS-035 — Occasion-Aware Wear History (occasion_key + outfit_id)
--
-- Per docs/tickets/SS-035-design.md §3. Forward-only; 001_initial.sql and
-- 006_wardrobe_item_wears.sql are NEVER edited (BL-060). Depends on SS-015
-- (006_wardrobe_item_wears.sql) and SS-025 (007/008 — the occasion
-- normalisation contract this migration reuses, not re-derives).
--
-- Wave 1.5 map (BL-110's incident note, renumbered 2026-07-31): 012 SS-029,
-- 013 SS-033, 014 SS-034, 015 this ticket, 016 SS-036.
--
-- Live PostgreSQL major version: [VERIFIED 2026-08-04 — SELECT version(),
-- current_setting('server_version_num') run directly against the linked
-- project mefpfykuinasgkpfhmzk: PostgreSQL 17.6, server_version_num=170006.
-- Confirmed PG15+, so this migration takes the primary path (design §3.3
-- onward), NOT the <15 fallback in design §3.8.] This migration is NOT
-- pushed to the live project by this phase (BL-110 -- the push is
-- serialized against sibling Wave 1.5 worktrees SS-034/SS-036 and left for
-- QA to coordinate, per this ticket's own instructions).
--
-- Builds the read substrate for Engine v2 / SS-020's stage-③ novelty term:
-- occasion_key (which occasion a wear was FOR) and outfit_id (which outfit
-- it was part of), both nullable/additive on wardrobe_item_wears. Nothing
-- in this repo calls public.wear_recency() yet -- BL-119. Does NOT touch
-- backend/services/outfit_suggestion_service.py or
-- backend/services/styling_rules_engine.py (BL-096's landmine).
-- ============================================================

-- ------------------------------------------------------------
-- 3.1 Version gate -- FIRST statement in the file. Two statements below
-- need PostgreSQL 15+: UNIQUE NULLS NOT DISTINCT (3.3) and the
-- column-list ON DELETE SET NULL (outfit_id) form (3.4). Without this
-- gate, a <15 server would fail with a bare syntax error partway through
-- the file instead of a named cause up front.
-- ------------------------------------------------------------
DO $$
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'SS-035 requires PostgreSQL 15+ (UNIQUE NULLS NOT DISTINCT, ON DELETE SET NULL (column)); this server reports %. Use the documented <15 fallback in docs/tickets/SS-035-design.md 3.8.',
      current_setting('server_version');
  END IF;
END $$;

-- ------------------------------------------------------------
-- 3.2 Derived-cache guard (AC #5), part 1: snapshot BEFORE any change in
-- this file. Plain TEMP table, deliberately NOT ON COMMIT DROP -- whether
-- the Supabase CLI wraps this migration in a single transaction is not
-- something this file should depend on; a session-scoped temp table is
-- correct either way, and it is dropped explicitly at the end of this
-- file (3.11).
-- ------------------------------------------------------------
CREATE TEMP TABLE ss035_wear_stats_before AS
  SELECT id, wear_count, last_worn_at, cost_per_wear FROM public.wardrobe_items;

-- ------------------------------------------------------------
-- 3.4 (executed before 3.3 -- the widened constraint below references
-- occasion_key, so the column must exist first) The two new columns.
-- Both nullable, no default: this IS AC #7's backfill -- every
-- pre-existing row gets occasion_key = NULL (= unknown occasion) with no
-- UPDATE statement, and NULL is a permanent, valid, first-class state.
-- ------------------------------------------------------------
ALTER TABLE public.wardrobe_item_wears
  ADD COLUMN occasion_key TEXT,
  ADD COLUMN outfit_id    UUID;

-- The shape CHECK is what stops a second "unknown" bucket forming: without
-- it an empty string could be stored, and '' and NULL would be two
-- distinct non-occasions under the widened key below. Byte-identical to
-- occasions.key's own CHECK (007_occasions_registry.sql:37). Because the
-- normalisation trigger (3.6) runs BEFORE this CHECK is evaluated and
-- returns NULL for anything that normalises to nothing, this CHECK can
-- never reject a user's raw input -- it only pins the trigger's output
-- shape.
ALTER TABLE public.wardrobe_item_wears
  ADD CONSTRAINT wardrobe_item_wears_occasion_key_shape_check
    CHECK (occasion_key IS NULL OR occasion_key ~ '^[a-z][a-z0-9_]*$');

-- ------------------------------------------------------------
-- 3.3 The widened uniqueness constraint -- the whole risk of this ticket.
--
-- NULLS NOT DISTINCT is the entire BL-071 preservation mechanism: under
-- the default NULLS DISTINCT, (item, today, NULL) could be inserted an
-- unbounded number of times -- every repeat tap of the one-tap "Mark
-- Worn" button (which writes NULL) would insert a new row and inflate
-- wear_count, i.e. exactly the complaint SS-015 was built to fix, silently
-- reintroduced by a widening that looks conservative.
--
-- This is a WIDENING (adds a column to the key), so no existing row can
-- violate it -- today at most one row exists per (item_id, worn_on); no
-- data cleanup, no NOT VALID/VALIDATE dance needed.
--
-- Constraint name changes deliberately: wardrobe_item_wears_one_per_day is
-- now a false description.
--
-- Ordering note: trg_wardrobe_item_wears_normalize_occasion_key (3.6) is
-- BEFORE INSERT OR UPDATE, and Postgres evaluates BEFORE row triggers
-- before constraint checks -- so 'Work'/'work'/'office' all become
-- 'office' BEFORE uniqueness is tested, and a same-day repeat under any
-- spelling collapses.
-- ------------------------------------------------------------
ALTER TABLE public.wardrobe_item_wears
  DROP CONSTRAINT wardrobe_item_wears_one_per_day;

ALTER TABLE public.wardrobe_item_wears
  ADD CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion
    UNIQUE NULLS NOT DISTINCT (item_id, worn_on, occasion_key);

-- ------------------------------------------------------------
-- 3.4 (continued) outfit_id's composite FK, this repo's established
-- convention (006:22-24's precedent, which required 006:13-14's
-- UNIQUE (id, user_id) on wardrobe_items).
--
-- Prerequisite for the composite FK below; additive, mirrors 006:13-14.
-- Confirmed live before adding this constraint (design §8 step 2): 0 rows
-- in outfits, so there is no data-shape risk either way
-- [VERIFIED 2026-08-04 -- ripgrep over this worktree: nothing in mobile/,
-- backend/ or supabase/functions/ writes outfits; consistent with
-- SS-025-design.md §6.4's "0 rows, no code"].
-- ------------------------------------------------------------
ALTER TABLE public.outfits
  ADD CONSTRAINT outfits_id_user_id_key UNIQUE (id, user_id);

-- ON DELETE SET NULL (outfit_id), WITH the column list, is mandatory --
-- not a stylistic choice. A bare ON DELETE SET NULL on a composite FK
-- sets EVERY referencing column to NULL, including user_id, which is NOT
-- NULL (006:19). Deleting an outfit would then fail with a not-null
-- violation, breaking AC #2 ("deleting that outfit does not delete or
-- alter the wear row") in the noisiest possible way. The single-column
-- form is the PostgreSQL 15 feature gated in 3.1.
--
-- ON DELETE SET NULL, never CASCADE: the wear happened even if the outfit
-- is later deleted; cascading would delete real wear rows, which the
-- AFTER DELETE trigger (006:78-80, untouched) would then turn into a
-- lowered wear_count and a silently RAISED cost_per_wear.
--
-- MATCH SIMPLE (the default) is what makes a NULL outfit_id legal --
-- with any referencing column NULL, the constraint is not checked, so the
-- overwhelmingly common "no outfit" case costs nothing.
ALTER TABLE public.wardrobe_item_wears
  ADD CONSTRAINT wardrobe_item_wears_outfit_fk
    FOREIGN KEY (outfit_id, user_id)
    REFERENCES public.outfits (id, user_id)
    ON DELETE SET NULL (outfit_id);

-- ------------------------------------------------------------
-- 3.5 Indexes. 006:31's idx_item_wears_item_worn_on and 006:32's
-- idx_item_wears_user_id are KEPT UNCHANGED; the widened constraint
-- brings its own (item_id, worn_on, occasion_key) index with it.
-- ------------------------------------------------------------

-- wear_recency()'s occasion-filtered aggregate.
CREATE INDEX idx_item_wears_user_occasion_worn
  ON public.wardrobe_item_wears (user_id, occasion_key, worn_on DESC);

-- Load-bearing, not speculative: Postgres does not automatically index the
-- referencing side of a foreign key, and every DELETE FROM outfits now
-- scans wardrobe_item_wears to apply SET NULL (same lesson SS-033 §3.3
-- recorded for its own cascade path). Partial because until SS-020/SS-023
-- exist, ~100% of rows have NULL here and indexing them buys nothing.
CREATE INDEX idx_item_wears_outfit_id
  ON public.wardrobe_item_wears (outfit_id) WHERE outfit_id IS NOT NULL;

-- ------------------------------------------------------------
-- 3.6 occasion_key normalisation trigger -- the new BL-078 boundary
-- (boundary 7 in SS-025 §6.4's matrix). A DEDICATED function, not a
-- reuse of 008's occasion_scalar_normalize_trigger, which is hardcoded
-- to a column literally named `occasion` and cannot be reused.
-- Parameterising it via TG_ARGV would require EXECUTE (dynamic SQL)
-- inside a SECURITY DEFINER function, which 007_occasions_registry.sql:
-- 166-171 forbids in capitals for this whole family of privileged
-- objects. Twenty duplicated lines is the cheaper trade.
--
-- Decision (design §2.3/§10, BL-078): this boundary ships with BOTH
-- halves from day one -- this DB trigger AND application-layer
-- normalisation in mobile/features/wardrobe/wardrobe.service.ts (reusing
-- the shipped resolveOccasionKey). Boundaries 4-6 got trigger-only
-- because no application write path existed yet; this one has a client
-- write path from day one.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.wear_occasion_key_normalize_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_norm TEXT;
BEGIN
  IF NEW.occasion_key IS NULL THEN
    RETURN NEW;
  END IF;

  v_norm := public.occasion_normalize_one(NEW.occasion_key);

  IF v_norm IS NOT NULL AND NOT public.occasion_is_known(v_norm) THEN
    PERFORM public.occasion_log_unknown(v_norm, TG_TABLE_NAME, NEW.user_id);
  END IF;

  NEW.occasion_key := v_norm;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_wardrobe_item_wears_normalize_occasion_key
  BEFORE INSERT OR UPDATE ON public.wardrobe_item_wears
  FOR EACH ROW EXECUTE FUNCTION public.wear_occasion_key_normalize_trigger();

-- Behaviour inherited from occasion_normalize_one (007:194-232), unchanged
-- and not re-derived: shape-normalise -> canonical key wins -> alias
-- lookup -> otherwise keep the normalised slug and record it in
-- occasion_unknown_tags. Never dropped, never a failed write. An
-- all-punctuation input normalises to NULL, i.e. "no occasion".
--
-- occasion_unknown_tags.sample_source now takes a fifth value,
-- 'wardrobe_item_wears'. The column is plain TEXT with no CHECK, so
-- nothing breaks; 007:85's enumerating comment is stale as of this
-- migration and is superseded by 3.9's COMMENT ON COLUMN below
-- (forward-only -- 007 is never edited).

-- ------------------------------------------------------------
-- 3.7 wear_recency() -- the queryable answer to AC #6. PostgREST cannot
-- express GROUP BY, and the two figures the AC distinguishes ("days since
-- worn at all" vs "days since worn FOR this occasion") are one aggregate
-- over the same rows, so this ships as a function.
--
-- SECURITY INVOKER (the default), UNLIKE the normalisation functions
-- above: this one only reads rows the caller can already read, so RLS
-- (user_owns_item_wears, 006:38-41) stays in force and a user cannot read
-- another user's history through it. p_user_id is an explicit filter IN
-- ADDITION TO RLS, not instead of it -- it exists so a future
-- service_role caller is still scoped.
--
-- NULL means unknown, never a match -- enforced by SQL's own
-- three-valued logic, not by a convention someone must remember:
-- w.occasion_key = p_occasion_key is NULL (not true) whenever either side
-- is NULL, so a backfilled row never satisfies the FILTER, and calling
-- with p_occasion_key => NULL returns last_worn_on_for_occasion = NULL /
-- wears_for_occasion = 0 for every item.
--
-- Returns DATES, not day-counts: "today" is an IST question, and a
-- server-side CURRENT_DATE is UTC. The caller subtracts against IST
-- today using backend/services/ist_window.py. Putting the timezone
-- decision in SQL would bury it.
--
-- Nothing calls this yet -- same posture as SS-033's substrate. Engine v2
-- / SS-020 wires it (BL-119 / BL-117).
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.wear_recency(
  p_user_id      UUID,
  p_occasion_key TEXT DEFAULT NULL
)
RETURNS TABLE (
  item_id                   UUID,
  last_worn_on              DATE,
  last_worn_on_for_occasion DATE,
  wears_for_occasion        INTEGER
)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
  SELECT w.item_id,
         MAX(w.worn_on)                                                    AS last_worn_on,
         MAX(w.worn_on) FILTER (WHERE w.occasion_key = p_occasion_key)     AS last_worn_on_for_occasion,
         COUNT(*) FILTER (WHERE w.occasion_key = p_occasion_key)::INTEGER  AS wears_for_occasion
  FROM public.wardrobe_item_wears w
  WHERE w.user_id = p_user_id
  GROUP BY w.item_id;
$$;

-- ------------------------------------------------------------
-- 3.9 Comments -- machine-checkable, per §7.1's
-- test_new_columns_and_constraint_carry_comments.
-- ------------------------------------------------------------
COMMENT ON COLUMN public.wardrobe_item_wears.occasion_key IS
  'SS-035. Occasion this wear was FOR, normalised at the DB boundary by '
  'trg_wardrobe_item_wears_normalize_occasion_key (aliases mapped, unknown slugs kept and '
  'recorded in occasion_unknown_tags with sample_source = ''wardrobe_item_wears''). '
  'Deliberately NO foreign key to occasions(key): an unknown slug must never fail the write, '
  'and history must survive a registry change. NULL means UNKNOWN OCCASION and must NEVER be '
  'treated as a match for any occasion (see public.wear_recency).';

COMMENT ON COLUMN public.wardrobe_item_wears.outfit_id IS
  'SS-035. Outfit this wear was part of. ON DELETE SET NULL (outfit_id), never CASCADE: the '
  'wear happened even if the outfit is later deleted, and cascading would corrupt wear_count '
  'and the generated cost_per_wear. No writer exists yet - SS-020/SS-023 own it.';

COMMENT ON CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion ON public.wardrobe_item_wears IS
  'SS-035, widened from SS-015''s UNIQUE (item_id, worn_on). NULLS NOT DISTINCT is load-bearing: '
  'without it, unlimited NULL-occasion rows per item per day would re-open BL-071 by letting '
  'repeat "Mark Worn" taps inflate wear_count and halve cost_per_wear.';

-- ------------------------------------------------------------
-- 3.2 Derived-cache guard (AC #5), part 2: self-verifying assertion,
-- the last statement before the temp table is dropped. Same fail-loudly
-- posture as 008_occasion_columns_to_text.sql:104-116's GIN-survival
-- guard. IS DISTINCT FROM, not <>, so a NULL->NULL comparison is
-- correctly "same" and a NULL->value change is correctly "different".
-- Expected to pass trivially (ADD COLUMN with no default is a
-- catalogue-only operation, and nothing here touches wardrobe_items other
-- than via the new outfits/wardrobe_item_wears constraints) -- the guard
-- exists because "expected to pass" is not "passed".
-- ------------------------------------------------------------
DO $$
DECLARE v_bad INTEGER;
BEGIN
  SELECT count(*) INTO v_bad
  FROM ss035_wear_stats_before b
  JOIN public.wardrobe_items a ON a.id = b.id
  WHERE a.wear_count   IS DISTINCT FROM b.wear_count
     OR a.last_worn_at IS DISTINCT FROM b.last_worn_at
     OR a.cost_per_wear IS DISTINCT FROM b.cost_per_wear;
  IF v_bad > 0 THEN
    RAISE EXCEPTION 'SS-035 altered a derived wear statistic on % pre-existing row(s); AC #5 violated', v_bad;
  END IF;
  IF (SELECT count(*) FROM ss035_wear_stats_before)
     <> (SELECT count(*) FROM public.wardrobe_items) THEN
    RAISE EXCEPTION 'SS-035 changed the wardrobe_items row count';
  END IF;
END $$;

DROP TABLE ss035_wear_stats_before;

-- ============================================================
-- ROLLBACK (valid while nothing reads the new columns):
--   DROP FUNCTION IF EXISTS public.wear_recency(UUID, TEXT);
--   DROP TRIGGER IF EXISTS trg_wardrobe_item_wears_normalize_occasion_key ON public.wardrobe_item_wears;
--   DROP FUNCTION IF EXISTS public.wear_occasion_key_normalize_trigger();
--   DROP INDEX IF EXISTS idx_item_wears_outfit_id;
--   DROP INDEX IF EXISTS idx_item_wears_user_occasion_worn;
--   ALTER TABLE public.wardrobe_item_wears DROP CONSTRAINT wardrobe_item_wears_outfit_fk;
--   ALTER TABLE public.outfits DROP CONSTRAINT outfits_id_user_id_key;
--   ALTER TABLE public.wardrobe_item_wears DROP CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion;
--   ALTER TABLE public.wardrobe_item_wears DROP CONSTRAINT wardrobe_item_wears_occasion_key_shape_check;
--   ALTER TABLE public.wardrobe_item_wears DROP COLUMN outfit_id, DROP COLUMN occasion_key;
--   ALTER TABLE public.wardrobe_item_wears ADD CONSTRAINT wardrobe_item_wears_one_per_day UNIQUE (item_id, worn_on);
-- NOTE: the final statement FAILS if two same-day multi-occasion rows already exist. That is
-- correct - it means real user data now depends on the widening, and rolling back would have to
-- destroy a wear the user recorded. Resolve by hand, never by deleting rows to make it apply.
-- ============================================================
