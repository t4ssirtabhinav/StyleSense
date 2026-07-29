-- ============================================================
-- SS-025 — Occasion Taxonomy & Extensibility Migration
-- STEP 2 of 3: MIGRATE (lossless cast + normalisation triggers)
--
-- Per docs/tickets/SS-025-design.md §4. Forward-only; 001_initial.sql is
-- never edited.
--
-- Old clients keep working across this step: PostgREST serialises both an
-- ENUM and a TEXT column as a JSON string, so a pre-migration mobile build
-- reading occasion_tags sees an identical payload.
-- [inference — QA verifies empirically per design §7.4 item 4 by reading a
-- wardrobe item over REST before and after and diffing the JSON.]
-- ============================================================

-- ------------------------------------------------------------
-- 1. The four occasion_type columns become TEXT / TEXT[] slugs.
--    Lossless: every stored value is already one of the 12 canonical keys.
-- ------------------------------------------------------------
ALTER TABLE wardrobe_items      ALTER COLUMN occasion_tags TYPE TEXT[] USING occasion_tags::text[];
ALTER TABLE outfits             ALTER COLUMN occasion      TYPE TEXT   USING occasion::text;
ALTER TABLE suggestion_sessions ALTER COLUMN occasion      TYPE TEXT   USING occasion::text;
ALTER TABLE social_posts        ALTER COLUMN occasion      TYPE TEXT   USING occasion::text;

-- ------------------------------------------------------------
-- 2. Normalisation triggers — the DB-level backstop under the
--    application-layer normalisers (design §6.4, the BL-078 matrix).
--
--    This is what lets the three write paths that do not exist yet
--    (outfits, social_posts, suggestion_sessions) be honestly called
--    covered today rather than deferred.
--
--    Normalisation happens inside the same statement as the write — it is
--    NOT a read-then-write, so this adds no third instance of the
--    BL-066/BL-036 concurrency bug class.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.occasion_tags_normalize_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  NEW.occasion_tags := public.occasion_normalize_array(
    NEW.occasion_tags, TG_TABLE_NAME, NEW.user_id
  );
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.occasion_scalar_normalize_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_norm TEXT;
BEGIN
  IF NEW.occasion IS NULL THEN
    RETURN NEW;
  END IF;

  v_norm := public.occasion_normalize_one(NEW.occasion);

  IF v_norm IS NOT NULL AND NOT public.occasion_is_known(v_norm) THEN
    PERFORM public.occasion_log_unknown(v_norm, TG_TABLE_NAME, NEW.user_id);
  END IF;

  NEW.occasion := v_norm;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_wardrobe_items_normalize_occasions
  BEFORE INSERT OR UPDATE ON wardrobe_items
  FOR EACH ROW EXECUTE FUNCTION public.occasion_tags_normalize_trigger();

CREATE TRIGGER trg_outfits_normalize_occasion
  BEFORE INSERT OR UPDATE ON outfits
  FOR EACH ROW EXECUTE FUNCTION public.occasion_scalar_normalize_trigger();

CREATE TRIGGER trg_suggestion_sessions_normalize_occasion
  BEFORE INSERT OR UPDATE ON suggestion_sessions
  FOR EACH ROW EXECUTE FUNCTION public.occasion_scalar_normalize_trigger();

CREATE TRIGGER trg_social_posts_normalize_occasion
  BEFORE INSERT OR UPDATE ON social_posts
  FOR EACH ROW EXECUTE FUNCTION public.occasion_scalar_normalize_trigger();

-- ------------------------------------------------------------
-- 3. GIN-survival guard — fails the migration loudly rather than silently
--    losing the hot "filter my wardrobe by occasion" index.
--
--    [inference, not verified — Postgres rebuilds indexes on a column whose
--    type is altered, and array_ops is valid for both occasion_type[] and
--    text[], so idx_wardrobe_occasions should survive as a GIN index
--    automatically. This DO block converts that inference into a hard
--    failure if it is wrong. If the guard fires, recreate the index
--    explicitly rather than reverting the type change:
--      CREATE INDEX idx_wardrobe_occasions
--        ON wardrobe_items USING GIN(occasion_tags);]
-- ------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename  = 'wardrobe_items'
      AND indexname  = 'idx_wardrobe_occasions'
      AND indexdef ILIKE '%using gin%'
  ) THEN
    RAISE EXCEPTION 'idx_wardrobe_occasions missing or no longer GIN after type change';
  END IF;
END
$$;

-- ============================================================
-- ROLLBACK: revert 008 (valid while every stored value is still one of the
-- 12 canonical enum keys — i.e. before 009 has dropped the type)
--
--   DROP TRIGGER IF EXISTS trg_social_posts_normalize_occasion        ON social_posts;
--   DROP TRIGGER IF EXISTS trg_suggestion_sessions_normalize_occasion ON suggestion_sessions;
--   DROP TRIGGER IF EXISTS trg_outfits_normalize_occasion             ON outfits;
--   DROP TRIGGER IF EXISTS trg_wardrobe_items_normalize_occasions     ON wardrobe_items;
--   DROP FUNCTION IF EXISTS public.occasion_scalar_normalize_trigger();
--   DROP FUNCTION IF EXISTS public.occasion_tags_normalize_trigger();
--
--   ALTER TABLE social_posts        ALTER COLUMN occasion      TYPE occasion_type   USING occasion::occasion_type;
--   ALTER TABLE suggestion_sessions ALTER COLUMN occasion      TYPE occasion_type   USING occasion::occasion_type;
--   ALTER TABLE outfits             ALTER COLUMN occasion      TYPE occasion_type   USING occasion::occasion_type;
--   ALTER TABLE wardrobe_items      ALTER COLUMN occasion_tags TYPE occasion_type[] USING occasion_tags::occasion_type[];
-- ============================================================
