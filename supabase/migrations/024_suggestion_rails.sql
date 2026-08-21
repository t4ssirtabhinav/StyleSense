-- ============================================================
-- SS-048 -- Rail Presets & Precompute Job
--
-- Per docs/tickets/SS-048-design.md's "Concrete values to use, not invent".
-- New table only -- no existing table altered. One row per (user_id,
-- rail_key), upserted by backend/services/rail_precompute_service.py on
-- every recompute; read by GET /suggestion-rails (a pure read, no writes).
--
-- engine_version is NULL for the two query-layer rails (never_tried_pairs,
-- not_yet_worn -- backend/services/suggestion_rails_query.py, zero
-- services.engine_v2* imports) and ENGINE_VERSION ("engine-v2") for the two
-- engine-backed rails (todays_picks, newest_pieces -- sliced from a single
-- EngineV2.generate_portfolio call). Used by the staleness check to force a
-- recompute when the stored engine_version no longer matches the live one,
-- regardless of computed_at recency (design doc's edge cases).
--
-- RLS mirrors wardrobe_items' user_owns_wardrobe FOR ALL policy exactly
-- (001_initial.sql:164-165) -- fully private to the row's own owner, no
-- broader-than-owner read path.
--
-- Apply via: supabase db push (linked project).
-- ============================================================

CREATE TABLE IF NOT EXISTS suggestion_rails (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rail_key       TEXT NOT NULL CHECK (rail_key IN
                   ('todays_picks', 'never_tried_pairs', 'not_yet_worn', 'newest_pieces')),
  computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  engine_version TEXT,
  payload        JSONB NOT NULL DEFAULT '{"items": []}'::jsonb,
  CONSTRAINT uq_suggestion_rails_user_rail UNIQUE (user_id, rail_key)
);

CREATE INDEX IF NOT EXISTS idx_suggestion_rails_user ON suggestion_rails (user_id);

ALTER TABLE suggestion_rails ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_owns_rails" ON suggestion_rails
  FOR ALL USING (auth.uid() = user_id);

COMMENT ON TABLE suggestion_rails IS
  'SS-048. Precomputed home-screen rail presets (todays_picks/never_tried_pairs/not_yet_worn/newest_pieces), one row per (user_id, rail_key). Written by backend/services/rail_precompute_service.py, read by GET /suggestion-rails (pure read, no side effects).';
COMMENT ON COLUMN suggestion_rails.engine_version IS
  'NULL for the two query-layer rails (never_tried_pairs, not_yet_worn -- no engine involvement). ENGINE_VERSION ("engine-v2") for todays_picks/newest_pieces. A non-NULL value that no longer matches the live ENGINE_VERSION forces a recompute regardless of computed_at recency.';

-- ============================================================
-- ROLLBACK: revert 024 (safe -- new table only, no existing table altered,
-- no data loss to any other table on drop).
--
--   DROP TABLE IF EXISTS suggestion_rails;
-- ============================================================
