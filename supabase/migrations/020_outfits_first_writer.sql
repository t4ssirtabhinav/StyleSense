-- SS-023 -- first writer to `outfits` (created in 001_initial.sql, never
-- written by any code path to date). Forward-only; 001 is NEVER edited
-- (BL-060). Every statement below is additive or a tightening that is safe
-- ONLY because the table is empty -- Developer confirmed
-- `SELECT count(*) FROM outfits` is 0 on the linked project
-- (mefpfykuinasgkpfhmzk) immediately before writing this migration; see
-- docs/worklog/SS-023.md for the recorded result.

ALTER TABLE outfits
  ADD COLUMN session_id         UUID REFERENCES suggestion_sessions(id) ON DELETE SET NULL,
  ADD COLUMN outfit_fingerprint TEXT,
  ADD COLUMN engine_version     TEXT,
  ADD COLUMN effort_tier        TEXT,
  ADD COLUMN reasoning_language TEXT,
  ADD COLUMN items_snapshot     JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE outfits
  ALTER COLUMN user_id SET NOT NULL,                       -- safe: table empty; a NULL
                                                           -- user_id row is invisible to
                                                           -- the RLS predicate anyway
  ADD CONSTRAINT outfits_item_ids_nonempty_check
    CHECK (item_ids IS NULL OR array_length(item_ids, 1) >= 1),
  ADD CONSTRAINT outfits_fingerprint_shape_check
    CHECK (outfit_fingerprint IS NULL OR outfit_fingerprint ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT outfits_effort_tier_check
    CHECK (effort_tier IS NULL OR effort_tier IN ('E0','E1','E2','E3','E4')),
  ADD CONSTRAINT outfits_reasoning_language_check
    CHECK (reasoning_language IS NULL OR reasoning_language IN ('en','hi')),
  ADD CONSTRAINT outfits_user_rating_range_check
    CHECK (user_rating IS NULL OR user_rating BETWEEN 1 AND 5);

-- Idempotent save: a double swipe-right (double tap, retried request, offline
-- replay) collapses onto one row instead of creating a duplicate outfit.
-- Partial, so hand-curated outfits (SS-024+) with no fingerprint are unaffected.
CREATE UNIQUE INDEX uq_outfits_user_fingerprint
  ON outfits (user_id, outfit_fingerprint) WHERE outfit_fingerprint IS NOT NULL;

CREATE INDEX idx_outfits_user_created ON outfits (user_id, created_at DESC);
CREATE INDEX idx_outfits_session      ON outfits (session_id);
CREATE INDEX idx_outfits_item_ids     ON outfits USING GIN (item_ids);

COMMENT ON COLUMN outfits.items_snapshot IS
  'Denormalised {item_id, category, color_primary, image_path} per item AT SAVE TIME. '
  'Deliberate redundancy: item_ids is a plain UUID[] with NO foreign key (same posture as '
  'suggestion_impressions.item_ids, 013_suggestion_impressions.sql:129-132), so deleting a '
  'wardrobe item cannot erase or corrupt a saved outfit. This snapshot is what lets a saved '
  'outfit still RENDER after one of its items is deleted -- resolving the edge case SS-014 and '
  'SS-015 both deferred as forward-looking (docs/tickets/SS-015-design.md:208).';
COMMENT ON COLUMN outfits.session_id IS
  'Provenance: which suggestion_sessions row produced this outfit. Nullable and ON DELETE SET '
  'NULL because SS-033s 180-day retention purge (public.purge_suggestion_logs) will delete the '
  'session long before the user deletes the outfit -- an outfit must survive its own provenance.';

-- RLS: DELIBERATELY UNCHANGED. `user_owns_outfits` (001_initial.sql:168) stays
-- FOR ALL. See docs/tickets/SS-023-design.md section 3 for why this ticket
-- does NOT repeat 013's write-policy removal here.

-- ============================================================
-- ROLLBACK (safe only while outfits is still empty):
--   DROP INDEX IF EXISTS idx_outfits_item_ids;
--   DROP INDEX IF EXISTS idx_outfits_session;
--   DROP INDEX IF EXISTS idx_outfits_user_created;
--   DROP INDEX IF EXISTS uq_outfits_user_fingerprint;
--   ALTER TABLE outfits
--     DROP CONSTRAINT IF EXISTS outfits_user_rating_range_check,
--     DROP CONSTRAINT IF EXISTS outfits_reasoning_language_check,
--     DROP CONSTRAINT IF EXISTS outfits_effort_tier_check,
--     DROP CONSTRAINT IF EXISTS outfits_fingerprint_shape_check,
--     DROP CONSTRAINT IF EXISTS outfits_item_ids_nonempty_check,
--     ALTER COLUMN user_id DROP NOT NULL,
--     DROP COLUMN IF EXISTS items_snapshot,
--     DROP COLUMN IF EXISTS reasoning_language,
--     DROP COLUMN IF EXISTS effort_tier,
--     DROP COLUMN IF EXISTS engine_version,
--     DROP COLUMN IF EXISTS outfit_fingerprint,
--     DROP COLUMN IF EXISTS session_id;
-- ============================================================
