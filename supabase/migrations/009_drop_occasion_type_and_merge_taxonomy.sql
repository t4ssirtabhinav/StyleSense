-- ============================================================
-- SS-025 — Occasion Taxonomy & Extensibility Migration
-- STEP 3 of 3: CONTRACT (merge the split-brain vocabulary, drop the enum
--              and the superseded onboarding table)
--
-- Per docs/tickets/SS-025-design.md §4. Forward-only; 001_initial.sql is
-- never edited.
--
-- The two vocabularies that were separate until now:
--   - `occasion_type` ENUM (001_initial.sql:18) — the wardrobe-tagging one
--   - `occasion_types` TABLE (003_onboarding_taxonomies.sql:26) — the
--     onboarding-wizard one, 9 rows, using `wedding`/`date` where the enum
--     uses `wedding_guest`/`date_night`
-- become one: the `occasions` registry from 007, with permanent alias rows
-- covering the two disagreements.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Backfill users.style_preferences.occasions_priority through the alias
--    map, PRESERVING ORDER. This is the step that merges the onboarding
--    vocabulary into the canonical one (wedding -> wedding_guest,
--    date -> date_night). Missing this would silently blank a user's saved
--    onboarding priorities once the pickers start rendering canonical keys.
--
--    Users with no `occasions_priority` key produce no lateral rows and are
--    left untouched (jsonb_set with create_missing = false). The
--    jsonb_typeof guard skips any row whose value is not a JSON array
--    rather than erroring the whole migration on it.
--
--    The pre-state of every affected row is captured in
--    docs/worklog/SS-025.md BEFORE this migration is applied (design §7.1).
-- ------------------------------------------------------------
UPDATE users u
SET style_preferences = jsonb_set(u.style_preferences, '{occasions_priority}', m.mapped, false)
FROM (
  SELECT u2.id,
         jsonb_agg(COALESCE(a.occasion_key, e.value) ORDER BY e.ord) AS mapped
  FROM users u2
  CROSS JOIN LATERAL jsonb_array_elements_text(u2.style_preferences->'occasions_priority')
       WITH ORDINALITY AS e(value, ord)
  LEFT JOIN occasion_aliases a ON a.alias = e.value
  WHERE jsonb_typeof(u2.style_preferences->'occasions_priority') = 'array'
  GROUP BY u2.id
) m
WHERE u.id = m.id;

-- ------------------------------------------------------------
-- 2. Drop the occasion_type ENUM — guarded, so this fails loudly if 008
--    did not fully complete rather than erroring out mid-way with a
--    confusing dependency message.
-- ------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_depend d
    JOIN pg_type t ON t.oid = d.refobjid
    WHERE t.typname IN ('occasion_type', '_occasion_type')
      AND d.deptype = 'n'
      AND d.classid = 'pg_attribute'::regclass
  ) THEN
    RAISE EXCEPTION 'occasion_type still has column dependencies — 008 did not complete';
  END IF;
END
$$;

DROP TYPE occasion_type;

-- ------------------------------------------------------------
-- 3. Drop the superseded 9-row onboarding taxonomy table.
--
--    This is the only genuinely destructive statement in the ticket. It is
--    safe here because (a) its only consumer,
--    mobile/features/onboarding/onboarding.taxonomies.service.ts, is
--    changed in this same PR to read `occasions` instead, and (b) its
--    content is fully reconstructible from 003_onboarding_taxonomies.sql —
--    transcribed verbatim into the rollback block below.
-- ------------------------------------------------------------
DROP TABLE occasion_types;

-- ============================================================
-- ROLLBACK: revert 009
--
-- 3'. Recreate occasion_types (transcribed verbatim from
--     003_onboarding_taxonomies.sql lines 26-31, 49, 54-55, 76-85):
--
--   CREATE TABLE occasion_types (
--     key         TEXT PRIMARY KEY,
--     label       TEXT NOT NULL,
--     sort_order  INTEGER NOT NULL,
--     active      BOOLEAN NOT NULL DEFAULT true
--   );
--
--   ALTER TABLE occasion_types ENABLE ROW LEVEL SECURITY;
--
--   CREATE POLICY "authenticated_read_occasion_types" ON occasion_types
--     FOR SELECT USING (auth.role() = 'authenticated');
--
--   INSERT INTO occasion_types (key, label, sort_order) VALUES
--     ('office',   'Office',   1),
--     ('wedding',  'Wedding',  2),
--     ('festival', 'Festival', 3),
--     ('casual',   'Casual',   4),
--     ('date',     'Date',     5),
--     ('party',    'Party',    6),
--     ('college',  'College',  7),
--     ('travel',   'Travel',   8),
--     ('puja',     'Puja',     9);
--
-- 2'. Recreate the ENUM (transcribed verbatim from 001_initial.sql:18-21).
--     Note: this only restores the TYPE. Re-pointing the four columns at it
--     is 008's rollback block, which must run after this.
--
--   CREATE TYPE occasion_type AS ENUM (
--     'office', 'casual', 'date_night', 'wedding_guest', 'festival',
--     'puja', 'party', 'travel', 'workout', 'beach', 'formal_event', 'college'
--   );
--
-- 1'. Reverse the alias backfill (wedding_guest -> wedding,
--     date_night -> date). Only meaningful if the onboarding UI is also
--     reverted to the 9-row vocabulary; the canonical keys are otherwise
--     valid everywhere.
--
--   UPDATE users u
--   SET style_preferences = jsonb_set(u.style_preferences, '{occasions_priority}', m.mapped, false)
--   FROM (
--     SELECT u2.id,
--            jsonb_agg(
--              CASE e.value
--                WHEN 'wedding_guest' THEN 'wedding'
--                WHEN 'date_night'    THEN 'date'
--                ELSE e.value
--              END ORDER BY e.ord) AS mapped
--     FROM users u2
--     CROSS JOIN LATERAL jsonb_array_elements_text(u2.style_preferences->'occasions_priority')
--          WITH ORDINALITY AS e(value, ord)
--     WHERE jsonb_typeof(u2.style_preferences->'occasions_priority') = 'array'
--     GROUP BY u2.id
--   ) m
--   WHERE u.id = m.id;
-- ============================================================
