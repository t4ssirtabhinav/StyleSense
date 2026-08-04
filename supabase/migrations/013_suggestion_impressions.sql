-- ============================================================
-- SS-033 — Suggestion Impression & Outcome Logging
--
-- Per docs/tickets/SS-033-design.md §3. Forward-only; 001_initial.sql is
-- NEVER edited (BL-060). Depends on SS-025 (008_occasion_columns_to_text.sql
-- — suggestion_sessions.occasion is already TEXT with a normalisation
-- trigger) and SS-026 (010_app_config.sql — the retention window lives in
-- app_config).
--
-- Renumbered 013 (2026-07-31, per BL-110's incident note): SS-029 shipped
-- live as migration 012, not 011 as originally assumed — 011 was
-- independently claimed by SS-028's 011_seed_ai_routing_config.sql. Wave
-- 1.5 map: 012 SS-029, 013 this ticket, 014 SS-034, 015 SS-035, 016 SS-036.
--
-- Builds the write substrate for three surfaces: request context (extends
-- suggestion_sessions additively), candidates shown (suggestion_impressions,
-- one row per candidate), and user reaction (suggestion_outcomes, multiple
-- rows per impression, ordered). Substrate + tests only — no code path in
-- this repo writes these tables yet; backend/services/outfit_suggestion_service.py
-- is deliberately NOT touched (BL-096's landmine, BL-102 precedent) — SS-020
-- does the wiring.
--
-- pg_cron verification (design §9 Q1, docs/OPERATOR_RULEBOOK.md §E):
-- `[VERIFIED via repo evidence, 2026-08-03 — "init documents/handoff.md"
-- Section 8: "pg_cron (v1.6.4) and pg_net (v0.20.3) both installed and
-- active in production DB"; cost-monitor and weekly-report are recorded
-- there as already DEPLOYED with real pg_cron schedules (`30 17 * * *` /
-- `30 2 * * 1`). This is documentary evidence written before this session,
-- not a live SQL query run THIS session — this environment has no
-- SUPABASE_DB_URL/psycopg2 to query pg_extension/cron.job directly, and
-- BL-110 means this migration is not being pushed by this phase either. QA
-- must still confirm live per design §8 item 6-7 (SELECT * FROM cron.job
-- WHERE jobname = 'purge_suggestion_logs' after push).]` The DO block below
-- is written defensively regardless (loud WARNING, not a failed migration,
-- if pg_cron turns out to be unavailable after all).
-- ============================================================

-- ------------------------------------------------------------
-- 3.1 Extend suggestion_sessions (additive). weather_data/cache_key already
-- exist (001_initial.sql) — reused, not duplicated.
-- ------------------------------------------------------------

ALTER TABLE suggestion_sessions
  ADD COLUMN engine_version       TEXT,
  ADD COLUMN effort_tier          TEXT,
  ADD COLUMN tier                 TEXT,
  ADD COLUMN config_snapshot_hash TEXT,
  ADD COLUMN candidate_count      SMALLINT,
  ADD COLUMN request_id           UUID,
  ADD COLUMN latency_ms           INTEGER,
  ADD COLUMN cost_incurred        BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN zero_cost_reason     TEXT;

-- Named constraints so a failure names itself. Four decisions recorded in
-- design §3.1: (1) cost_incurred defaults true (a forgetful writer
-- over-reports spend, never silently under-reports — alerting fails loud);
-- (2) effort_tier is CHECK-enumerated (a fixed 5-tier dial), tier is a
-- shape-only regex (a historical snapshot of plan_tier, which may gain
-- values later — a value CHECK here would make a future plan tier fail an
-- audit-log write); (3) zero_cost_reason is enumerated and REQUIRED when
-- cost_incurred=false, paired with a consistency CHECK so the two columns
-- can never disagree; (4) request_id/latency_ms are added now because they
-- cannot be backfilled later.
ALTER TABLE suggestion_sessions
  ADD CONSTRAINT suggestion_sessions_effort_tier_check
    CHECK (effort_tier IS NULL OR effort_tier IN ('E0','E1','E2','E3','E4')),
  ADD CONSTRAINT suggestion_sessions_tier_shape_check
    CHECK (tier IS NULL OR tier ~ '^[a-z][a-z0-9_]*$'),
  ADD CONSTRAINT suggestion_sessions_candidate_count_check
    CHECK (candidate_count IS NULL OR candidate_count >= 0),
  ADD CONSTRAINT suggestion_sessions_latency_check
    CHECK (latency_ms IS NULL OR latency_ms >= 0),
  ADD CONSTRAINT suggestion_sessions_zero_cost_reason_check
    CHECK (zero_cost_reason IS NULL OR zero_cost_reason IN
      ('cache_hit','degraded_e0','rules_only','budget_denied','no_provider_call')),
  ADD CONSTRAINT suggestion_sessions_cost_marker_consistency_check
    CHECK ( (cost_incurred AND zero_cost_reason IS NULL)
         OR (NOT cost_incurred AND zero_cost_reason IS NOT NULL) );

-- No new trigger here — SS-025's trg_suggestion_sessions_normalize_occasion
-- (008_occasion_columns_to_text.sql:83-85) already fires BEFORE INSERT OR
-- UPDATE and rewrites NEW.occasion through occasion_normalize_one. The
-- value read back may not be byte-identical to the one written (an alias
-- normalises to its canonical key); callers must not assert round-trip
-- equality on occasion.

-- ------------------------------------------------------------
-- 3.2 Deprecate the two superseded columns — COMMENT, do not drop.
-- Both are NULL in every row today (nothing has ever written them); a
-- DROP COLUMN would invalidate the committed mobile/types/supabase.ts row
-- type. Dropped in a later CONTRACT migration once no reader exists
-- (BL-112), mirroring SS-025's EXPAND/MIGRATE/CONTRACT (007/008/009)
-- precedent.
-- ------------------------------------------------------------

COMMENT ON COLUMN suggestion_sessions.suggestions IS
  'DEPRECATED (SS-033, 2026-07-30). Superseded by the suggestion_impressions table, which '
  'stores one row per candidate with its score breakdown. Nothing has ever written this column. '
  'Do not write it; do not read it. Scheduled for removal in a later CONTRACT migration once '
  'mobile/types/supabase.ts no longer references it (see BL-112).';

COMMENT ON COLUMN suggestion_sessions.accepted_outfit_id IS
  'DEPRECATED (SS-033, 2026-07-30). A single-accepted-outfit precursor to suggestion_outcomes, '
  'which records saved/worn/dismissed/shuffled_away/shared per impression with ordering and '
  'permits multiple outcomes. Nothing has ever written this column. Use '
  'suggestion_outcomes.outcome_type = ''saved'' instead. Scheduled for removal in a later '
  'CONTRACT migration (see BL-112).';

-- ------------------------------------------------------------
-- 3.3 suggestion_impressions — one row per candidate outfit shown.
-- ------------------------------------------------------------

CREATE TABLE suggestion_impressions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id         UUID NOT NULL REFERENCES suggestion_sessions(id) ON DELETE CASCADE,
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rank               SMALLINT NOT NULL CHECK (rank >= 1),
  item_ids           UUID[] NOT NULL CHECK (array_length(item_ids, 1) >= 1),
  outfit_fingerprint TEXT NOT NULL CHECK (outfit_fingerprint ~ '^[0-9a-f]{64}$'),
  total_score        NUMERIC(6,5) NOT NULL CHECK (total_score >= 0 AND total_score <= 1),
  rule_scores        JSONB NOT NULL DEFAULT '[]'::jsonb,
  gap_flags          TEXT[] NOT NULL DEFAULT '{}',
  is_exploration     BOOLEAN NOT NULL DEFAULT false,
  strategy           TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT suggestion_impressions_session_rank_unique UNIQUE (session_id, rank)
);

-- item_ids is a plain UUID[] with NO foreign key — deliberate (design
-- §3.3): a wardrobe_items delete must be structurally incapable of erasing
-- impression history. Readers must tolerate a stale id resolving to
-- nothing.

CREATE INDEX idx_suggestion_impressions_user_created
  ON suggestion_impressions (user_id, created_at DESC);            -- "what did we show this user recently" (anti-repetition); also the RLS predicate's index
CREATE INDEX idx_suggestion_impressions_user_fingerprint
  ON suggestion_impressions (user_id, outfit_fingerprint, created_at DESC);  -- "have we shown this exact outfit to this user recently" (SS-023 regenerate AC)
CREATE INDEX idx_suggestion_impressions_session
  ON suggestion_impressions (session_id);                          -- session -> impressions join AND the FK's cascade-delete path (load-bearing for retention, see 3.6)
CREATE INDEX idx_suggestion_impressions_item_ids
  ON suggestion_impressions USING GIN (item_ids);                  -- forward-looking for SS-035's per-item novelty scoring; free to create now on an empty table

-- ------------------------------------------------------------
-- 3.4 suggestion_outcomes — user reactions to an impression, ordered,
-- multiple permitted.
-- ------------------------------------------------------------

CREATE TABLE suggestion_outcomes (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  impression_id      UUID NOT NULL REFERENCES suggestion_impressions(id) ON DELETE CASCADE,
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  outcome_type       TEXT NOT NULL CHECK (outcome_type IN
                       ('saved','worn','dismissed','shuffled_away','shared')),
  outfit_id          UUID REFERENCES outfits(id) ON DELETE SET NULL,
  dedupe_key         TEXT,
  client_occurred_at TIMESTAMPTZ,
  metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- outfit_id is ON DELETE SET NULL, deliberately NOT CASCADE (design §3.4):
-- the fact a user saved an outfit is historical truth even if they later
-- delete the outfit itself. Contrast user_id's ON DELETE CASCADE, the
-- right privacy default pre-launch.

CREATE UNIQUE INDEX uq_suggestion_outcomes_dedupe
  ON suggestion_outcomes (impression_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX idx_suggestion_outcomes_impression_order
  ON suggestion_outcomes (impression_id, created_at, id);
CREATE INDEX idx_suggestion_outcomes_user_type_created
  ON suggestion_outcomes (user_id, outcome_type, created_at DESC);

COMMENT ON TABLE suggestion_outcomes IS
  'User reactions to a suggestion_impressions row (SS-033): saved/worn/dismissed/shuffled_away/'
  'shared. Multiple rows per impression permitted; canonical order is '
  'COALESCE(client_occurred_at, created_at), created_at, id. Purged as a unit with its parent '
  'impression via ON DELETE CASCADE. Same purpose limitation and retention as '
  'suggestion_impressions.';

-- ------------------------------------------------------------
-- 3.5 RLS — read-own, and NO write policy at all.
-- ------------------------------------------------------------

ALTER TABLE suggestion_impressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE suggestion_outcomes    ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_reads_own_impressions" ON suggestion_impressions
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "user_reads_own_outcomes" ON suggestion_outcomes
  FOR SELECT USING (auth.uid() = user_id);

-- DELIBERATELY no INSERT/UPDATE/DELETE policy on either table, for any role.
-- With RLS enabled and no matching policy, every write from anon/authenticated
-- is denied; service_role bypasses RLS. ABSENCE OF A POLICY *IS* THE
-- WRITE-PROTECTION MECHANISM -- the 007_occasions_registry.sql:91-105 /
-- 010_app_config.sql shape. Do not "fix" this by adding a permissive write
-- policy.

-- The one non-additive statement in this migration (design §3.5, scrutinised
-- per OPERATOR_RULEBOOK.md §C2): 001_initial.sql:172 created
-- "user_owns_sessions" as FOR ALL, i.e. a client can today INSERT/UPDATE/
-- DELETE its own session rows. AC #4 requires read-only. Nothing in
-- mobile/, backend/, or supabase/functions/ writes suggestion_sessions
-- today other than the two Edge Functions' service_role count queries
-- (which bypass RLS regardless), so there is no client write path to
-- remove because there is no client write path — but leaving FOR ALL in
-- place would let a client cascade-delete its own impression/outcome
-- history or forge cost_incurred=true rows to drive the cost monitor.
DROP POLICY IF EXISTS "user_owns_sessions" ON suggestion_sessions;
CREATE POLICY "user_reads_own_sessions" ON suggestion_sessions
  FOR SELECT USING (auth.uid() = user_id);
-- ROLLBACK: DROP POLICY "user_reads_own_sessions" ON suggestion_sessions;
--           CREATE POLICY "user_owns_sessions"
--           ON suggestion_sessions FOR ALL USING (auth.uid() = user_id);

-- user_id is denormalised onto both new tables (so the RLS predicate is a
-- direct index seek, not a per-row correlated subquery on a 44M-row table)
-- but NEVER trusted from the writer — it is DERIVED by a BEFORE INSERT
-- trigger that overwrites whatever was sent, making a wrong user_id
-- structurally impossible rather than merely unlikely. Not SECURITY
-- DEFINER (unlike 008's normalisation functions): these only read a row
-- the writer (always service_role, which bypasses RLS) can already read.
-- BEFORE INSERT only — nothing UPDATEs these append-only tables.

CREATE OR REPLACE FUNCTION public.suggestion_impression_set_user_id()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  SELECT s.user_id INTO NEW.user_id
    FROM suggestion_sessions s WHERE s.id = NEW.session_id;
  IF NEW.user_id IS NULL THEN
    RAISE EXCEPTION 'suggestion_impressions.user_id is not derivable: session % has no user_id', NEW.session_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.suggestion_outcome_set_user_id()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  SELECT i.user_id INTO NEW.user_id
    FROM suggestion_impressions i WHERE i.id = NEW.impression_id;
  IF NEW.user_id IS NULL THEN
    RAISE EXCEPTION 'suggestion_outcomes.user_id is not derivable: impression % not found', NEW.impression_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_suggestion_impressions_set_user_id
  BEFORE INSERT ON suggestion_impressions
  FOR EACH ROW EXECUTE FUNCTION public.suggestion_impression_set_user_id();
CREATE TRIGGER trg_suggestion_outcomes_set_user_id
  BEFORE INSERT ON suggestion_outcomes
  FOR EACH ROW EXECUTE FUNCTION public.suggestion_outcome_set_user_id();

-- ------------------------------------------------------------
-- 3.6 Retention — 180 days rolling, config-driven, cascade-purged.
--
-- Scheduled batched DELETE, not partitioning (design §3.6): a range-
-- partitioned parent would force created_at into suggestion_outcomes' FK,
-- but an outcome legitimately arrives weeks after its impression, so
-- dropping an impression partition could orphan or fail on dependent
-- outcome rows — breaking the very "purge as a unit" requirement
-- partitioning was meant to satisfy. The delete-based purge satisfies it
-- STRUCTURALLY instead: deleting a suggestion_sessions row cascades to its
-- impressions and their outcomes in the same transaction, so nothing can
-- be orphaned because nothing is deleted independently.
-- ------------------------------------------------------------

-- The retention window lives in SS-026's app_config so it is
-- product-adjustable without a migration (BL-108). Coded default 180,
-- clamped to [30, 730], degrading to 180 on a missing or malformed row --
-- the same clamp-and-degrade posture as AppConfigService._clamp_ttl.
CREATE OR REPLACE FUNCTION public.suggestion_log_retention_days()
RETURNS INTEGER LANGUAGE plpgsql STABLE AS $$
DECLARE v INTEGER;
BEGIN
  BEGIN
    SELECT (value->>'days')::int INTO v FROM app_config
      WHERE key = 'suggestion_log_retention_days';
  EXCEPTION WHEN others THEN
    v := NULL;   -- malformed JSON / non-numeric text must never break the purge
  END;
  IF v IS NULL THEN v := 180; END IF;
  RETURN LEAST(730, GREATEST(30, v));
END;
$$;

-- Batched, with a hard ceiling (5000 x 200 = 1M sessions/invocation) so a
-- nightly run cannot take an unbounded lock or blow up WAL; a backlog
-- drains over consecutive nights instead. ORDER BY created_at makes it
-- oldest-first, which needs idx_suggestion_sessions_created (below). Not
-- SECURITY DEFINER: the only callers are pg_cron's job owner and
-- service_role, both of which already bypass RLS on app_config and can
-- delete.
CREATE OR REPLACE FUNCTION public.purge_suggestion_logs(
  p_batch_size INTEGER DEFAULT 5000,
  p_max_batches INTEGER DEFAULT 200
) RETURNS TABLE (sessions_deleted BIGINT, retention_days INTEGER, cutoff TIMESTAMPTZ)
LANGUAGE plpgsql AS $$
DECLARE
  v_days   INTEGER := public.suggestion_log_retention_days();
  v_cutoff TIMESTAMPTZ := now() - make_interval(days => v_days);
  v_total  BIGINT := 0;
  v_n      BIGINT;
  i        INTEGER := 0;
BEGIN
  LOOP
    i := i + 1;
    DELETE FROM suggestion_sessions
     WHERE id IN (SELECT id FROM suggestion_sessions
                   WHERE created_at < v_cutoff
                   ORDER BY created_at
                   LIMIT p_batch_size);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_total := v_total + v_n;
    EXIT WHEN v_n < p_batch_size OR i >= p_max_batches;
  END LOOP;
  RAISE LOG 'purge_suggestion_logs: deleted % sessions older than % (retention % days)',
    v_total, v_cutoff, v_days;
  RETURN QUERY SELECT v_total, v_days, v_cutoff;
END;
$$;

-- Scheduling — honesty over confidence (design §3.6/§9 Q1): pg_cron
-- availability on this project is backed by repo evidence (see the
-- migration header) but was not re-queried live this session. If the
-- extension is genuinely missing at apply time, this degrades to a loud
-- WARNING rather than a failed migration; purge_suggestion_logs() still
-- exists and is callable manually / via an Edge Function fallback (BL-113).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('purge_suggestion_logs', '0 22 * * *',
                          'SELECT public.purge_suggestion_logs();');
  ELSE
    RAISE WARNING 'pg_cron is not installed: purge_suggestion_logs() exists but is NOT SCHEDULED. Retention is unenforced until a scheduler is wired -- see SS-033-design.md 3.6 fallback.';
  END IF;
END $$;

-- Seed row and the purpose-limitation record. updated_by follows
-- 010_app_config.sql's convention of an explicit migration identity.
INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('suggestion_log_retention_days', '{"days": 180}'::jsonb, 'server',
   'Rolling retention window (days) for suggestion_sessions and its cascaded suggestion_impressions/suggestion_outcomes rows. Enforced nightly by public.purge_suggestion_logs(). Clamped to [30, 730] in SQL; a missing or malformed value degrades to 180. Stated purpose limitation: suggestion-quality measurement and personalization only. Product-adjustable via UPDATE, no migration needed (BL-108).',
   'migration:013_suggestion_impressions');

COMMENT ON TABLE suggestion_impressions IS
  'One row per candidate outfit shown to a user (SS-033). Append-only; no client write path. '
  'PURPOSE LIMITATION: suggestion-quality measurement and personalization only. RETENTION: '
  'rolling window from app_config.suggestion_log_retention_days (default 180 days), enforced by '
  'public.purge_suggestion_logs(). India DPDP Act applicability is UNVERIFIED -- see BL-108.';

-- New indexes on suggestion_sessions, each tied to one named query. The
-- first is a PARTIAL index matching cost-monitor's filter exactly, so the
-- BL-107 fix is an index-only count rather than a growing table scan.
CREATE INDEX idx_suggestion_sessions_costed_created
  ON suggestion_sessions (created_at DESC) WHERE cost_incurred;   -- cost-monitor's daily billable count
CREATE INDEX idx_suggestion_sessions_created
  ON suggestion_sessions (created_at);                            -- weekly-report total + the purge's oldest-first scan
CREATE INDEX idx_suggestion_sessions_user_created
  ON suggestion_sessions (user_id, created_at DESC);              -- per-user session history; the RLS SELECT predicate's index

-- ============================================================
-- ROLLBACK: revert 013 (destructive beyond the RLS policy swap already
-- noted above -- dropping the two new tables discards any rows already
-- logged; only run this before real traffic exists)
--
--   SELECT cron.unschedule('purge_suggestion_logs');  -- no-op if pg_cron wasn't available
--   DROP FUNCTION IF EXISTS public.purge_suggestion_logs(INTEGER, INTEGER);
--   DROP FUNCTION IF EXISTS public.suggestion_log_retention_days();
--   DELETE FROM app_config WHERE key = 'suggestion_log_retention_days';
--   DROP TRIGGER IF EXISTS trg_suggestion_outcomes_set_user_id   ON suggestion_outcomes;
--   DROP TRIGGER IF EXISTS trg_suggestion_impressions_set_user_id ON suggestion_impressions;
--   DROP FUNCTION IF EXISTS public.suggestion_outcome_set_user_id();
--   DROP FUNCTION IF EXISTS public.suggestion_impression_set_user_id();
--   DROP POLICY IF EXISTS "user_reads_own_sessions" ON suggestion_sessions;
--   CREATE POLICY "user_owns_sessions" ON suggestion_sessions FOR ALL USING (auth.uid() = user_id);
--   DROP TABLE IF EXISTS suggestion_outcomes;
--   DROP TABLE IF EXISTS suggestion_impressions;
--   DROP INDEX IF EXISTS idx_suggestion_sessions_costed_created;
--   DROP INDEX IF EXISTS idx_suggestion_sessions_created;
--   DROP INDEX IF EXISTS idx_suggestion_sessions_user_created;
--   ALTER TABLE suggestion_sessions
--     DROP CONSTRAINT IF EXISTS suggestion_sessions_effort_tier_check,
--     DROP CONSTRAINT IF EXISTS suggestion_sessions_tier_shape_check,
--     DROP CONSTRAINT IF EXISTS suggestion_sessions_candidate_count_check,
--     DROP CONSTRAINT IF EXISTS suggestion_sessions_latency_check,
--     DROP CONSTRAINT IF EXISTS suggestion_sessions_zero_cost_reason_check,
--     DROP CONSTRAINT IF EXISTS suggestion_sessions_cost_marker_consistency_check,
--     DROP COLUMN IF EXISTS engine_version,
--     DROP COLUMN IF EXISTS effort_tier,
--     DROP COLUMN IF EXISTS tier,
--     DROP COLUMN IF EXISTS config_snapshot_hash,
--     DROP COLUMN IF EXISTS candidate_count,
--     DROP COLUMN IF EXISTS request_id,
--     DROP COLUMN IF EXISTS latency_ms,
--     DROP COLUMN IF EXISTS cost_incurred,
--     DROP COLUMN IF EXISTS zero_cost_reason;
--   COMMENT ON COLUMN suggestion_sessions.suggestions IS NULL;
--   COMMENT ON COLUMN suggestion_sessions.accepted_outfit_id IS NULL;
-- ============================================================
