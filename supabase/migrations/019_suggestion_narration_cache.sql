-- ============================================================
-- SS-020 -- suggestion_narration_cache (the combination-signature cache)
--
-- Per docs/tickets/SS-020-design.md sections 3/4. THIS IS THE ONE-WAY DOOR
-- the raw ticket calls out by name ("cache keys are near-impossible to
-- change once a populated cache is live") -- the coarsening granularity
-- (colour bucketed to family, formality rounded to bands of 2) was
-- explicitly signed off by the user on 2026-08-07 (see
-- docs/worklog/SS-020.md's "Open questions -- signed off" entry) before
-- this migration was written for real.
--
-- What is cached: ONLY the LLM's narration prose for a coarsened, salted,
-- cross-user-shareable candidate-attribute signature -- NEVER Engine v2's
-- own per-user candidate selection (which stays 100% per-user, computed
-- fresh every request). No user_id column at all, by construction -- this
-- is the structural half of "not reversible into another user's wardrobe"
-- (the other half is backend/services/suggestion_narration_cache.py's
-- compute_narration_signature() never hashing raw item attributes or ids).
--
-- signature_hash is a salted HMAC-SHA256 hex digest (64 lowercase hex
-- chars), keyed on SUGGESTION_CACHE_SALT (a required, not-yet-provisioned
-- env var -- see docs/worklog/SS-020.md's Developer entry).
-- ============================================================

CREATE TABLE suggestion_narration_cache (
  signature_hash   TEXT PRIMARY KEY CHECK (signature_hash ~ '^[0-9a-f]{64}$'),
  occasion_key     TEXT NOT NULL,
  engine_version   TEXT NOT NULL,
  language         TEXT NOT NULL DEFAULT 'en',
  narrations       JSONB NOT NULL,            -- {"0": "...", "1": "...", ...} keyed by signature-array index, NEVER item_ids/user_id
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at       TIMESTAMPTZ NOT NULL,
  hit_count        INTEGER NOT NULL DEFAULT 0
);

COMMENT ON TABLE suggestion_narration_cache IS
  'SS-020 narration-only cache: shares LLM prose across users for a coarsened '
  '(category, colour_family_bucket, formality_band) candidate-set shape, '
  'never Engine v2''s own per-user candidate selection. No user_id/item_id '
  'column at all, by design -- see backend/services/suggestion_narration_cache.py.';

-- No user_id column at all, by construction -- this is the structural half
-- of "not reversible into another user's wardrobe" (the other half is
-- compute_narration_signature never hashing raw item attributes or ids).
-- RLS: default-deny for every client role (mirrors app_config's own
-- posture, SS-025/026's established precedent for non-user-owned tables
-- with zero client access) -- only service_role (this ticket's
-- SupabaseSuggestionNarrationCacheRepository) ever touches this table.
ALTER TABLE suggestion_narration_cache ENABLE ROW LEVEL SECURITY;
-- (no policies created -- default-deny is the policy)

CREATE INDEX idx_suggestion_narration_cache_expires_at
  ON suggestion_narration_cache (expires_at);

-- ============================================================
-- Cleanup: a pg_cron job deleting expired rows, mirroring SS-033's own
-- precedent (migration 013's purge_suggestion_logs) rather than inventing
-- a new cleanup mechanism. Honesty over confidence, same posture as 013:
-- if pg_cron is genuinely missing at apply time, this degrades to a loud
-- WARNING rather than a failed migration -- the function still exists and
-- is callable manually / via an Edge Function fallback.
-- ============================================================

CREATE OR REPLACE FUNCTION public.purge_suggestion_narration_cache(
  p_batch_size INTEGER DEFAULT 5000,
  p_max_batches INTEGER DEFAULT 200
) RETURNS TABLE (rows_deleted BIGINT)
LANGUAGE plpgsql AS $$
DECLARE
  v_total BIGINT := 0;
  v_n     BIGINT;
  i       INTEGER := 0;
BEGIN
  LOOP
    i := i + 1;
    DELETE FROM suggestion_narration_cache
     WHERE signature_hash IN (
       SELECT signature_hash FROM suggestion_narration_cache
        WHERE expires_at < now()
        ORDER BY expires_at
        LIMIT p_batch_size
     );
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_total := v_total + v_n;
    EXIT WHEN v_n < p_batch_size OR i >= p_max_batches;
  END LOOP;
  RAISE LOG 'purge_suggestion_narration_cache: deleted % expired rows', v_total;
  RETURN QUERY SELECT v_total;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('purge_suggestion_narration_cache', '15 * * * *',
                          'SELECT public.purge_suggestion_narration_cache();');
  ELSE
    RAISE WARNING 'pg_cron is not installed: purge_suggestion_narration_cache() exists but is NOT SCHEDULED. Expired rows accumulate until a scheduler is wired -- see SS-020-design.md section 4 fallback (mirrors SS-033/013''s own documented posture).';
  END IF;
END $$;

-- ============================================================
-- app_config seed row -- SUGGESTION_NARRATION_CACHE_TTL_SPEC's coded
-- default (backend/services/app_config_specs.py::SuggestionNarrationCacheTtlConfig)
-- matches this row exactly, so a missing/malformed row degrades to the
-- same 6h TTL.
-- ============================================================

INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('suggestion_narration_cache_ttl_seconds', '{"seconds": 21600}'::jsonb, 'server',
   'TTL (seconds) for suggestion_narration_cache rows -- 6 hours. Coded default in app_config_specs.py::SuggestionNarrationCacheTtlConfig matches this row exactly; a missing or malformed row degrades to the same 6h default. Product-adjustable via UPDATE, no migration needed.',
   'migration:019_suggestion_narration_cache');

-- ============================================================
-- ROLLBACK:
--
--   SELECT cron.unschedule('purge_suggestion_narration_cache');  -- no-op if pg_cron wasn't available
--   DROP FUNCTION IF EXISTS public.purge_suggestion_narration_cache(INTEGER, INTEGER);
--   DROP TABLE IF EXISTS suggestion_narration_cache;
--   DELETE FROM app_config WHERE key = 'suggestion_narration_cache_ttl_seconds';
-- ============================================================
