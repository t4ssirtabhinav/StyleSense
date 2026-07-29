-- ============================================================
-- SS-026 — Runtime Config Substrate (`app_config`)
--
-- Per docs/tickets/SS-026-design.md §3. Forward-only: 001_initial.sql is
-- NEVER edited (BL-060 — the CI drift check has a false-positive history;
-- do not feed it). Purely additive — a brand-new, empty table with zero
-- existing consumers and zero existing data touched.
--
-- Backend reads this table through exactly one typed accessor
-- (backend/services/app_config.py::AppConfigService) — never a raw table
-- read scattered across services. This migration seeds two demo-only keys
-- to prove the mechanism; it wires no real consumer (SS-028+ is that job).
-- ============================================================

-- ------------------------------------------------------------
-- Table
-- ------------------------------------------------------------

-- Six columns only -- the ticket's own AC list, transcribed verbatim
-- (design §3.1). `scope` doubles as the RLS visibility switch: 'server'
-- (default) is service_role-only; 'client_visible' on a specific row opts
-- THAT row into `authenticated` read access. Explicit, per-row, enumerated
-- opt-in -- never a wildcard or negation predicate.
CREATE TABLE app_config (
  key         TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  value       JSONB NOT NULL,
  scope       TEXT NOT NULL DEFAULT 'server' CHECK (scope IN ('server', 'client_visible')),
  description TEXT NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Nullable, no default (design §3.1) -- a fake default a lazy future
  -- writer never overrides would be indistinguishable from a deliberately
  -- recorded identity and would actively undermine "auditable". NULL is
  -- the honest signal "nobody recorded who" (BL-094 — not enforced by any
  -- constraint; a visible, not silent, audit-trail gap).
  updated_by  TEXT
);

-- No index beyond the primary key -- same reasoning as
-- 007_occasions_registry.sql §3.1's `occasions` table: this will be a
-- low-hundreds-of-rows table at most; a sequential scan is correct.

-- `updated_at` is enforced, not just conventional: a BEFORE UPDATE trigger
-- stamps now() unconditionally, so a writer that forgets to set it
-- explicitly still produces a truthful timestamp. Not SECURITY DEFINER --
-- this touches no other table, only the row already being written by
-- whoever already has UPDATE rights (service_role only, RLS below).
CREATE OR REPLACE FUNCTION public.app_config_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER app_config_set_updated_at
BEFORE UPDATE ON app_config
FOR EACH ROW EXECUTE FUNCTION public.app_config_touch_updated_at();

-- ------------------------------------------------------------
-- RLS — mirrors 007_occasions_registry.sql's established default-deny /
-- explicit-per-row-opt-in shape, not a new pattern invented here.
--
-- DELIBERATELY no INSERT/UPDATE/DELETE policy for anyone. Absence of a
-- policy IS the write-protection mechanism (service_role bypasses RLS
-- entirely; anon/authenticated get a hard deny on every write). Config
-- changes happen via the Supabase Dashboard SQL editor or a service_role
-- script -- never via the app on a user's behalf. Do not "fix" this by
-- adding a permissive write policy.
-- ------------------------------------------------------------
ALTER TABLE app_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_client_visible_config" ON app_config
  FOR SELECT USING (auth.role() = 'authenticated' AND scope = 'client_visible');

-- ------------------------------------------------------------
-- Seed — two demo-only keys (design §3.6). No model-routing table, no
-- cost-budget key, no pre-filter-threshold key is seeded here -- those are
-- SS-027/028/029's job; inventing product-facing values nobody has
-- specified is out of scope for this ticket.
--
-- updated_by is supplied as literal INSERT data, not a column default (see
-- above) -- migration seed rows get an honest, explicit identity.
-- ------------------------------------------------------------
INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('config_cache_ttl_seconds',
   '{"seconds": 60}'::jsonb, 'server',
   'In-process cache TTL for AppConfigService.snapshot(), seconds. Clamped to [5, 3600] in code -- a bad value here degrades to the clamp bound or the coded default, never to unreachable.',
   'migration:010_app_config'),
  ('gemini_quota_ceiling_rpm',
   '{"rpm": 15}'::jsonb, 'server',
   'Provider quota ceiling for Gemini tagging calls (requests/minute). Seeded conservative, matching backend/services/gemini_rate_limiter.py''s current hardcoded default, pending BL-076''s real paid-tier RPM verification. NOT YET CONSUMED -- GeminiRateLimiter still reads its own hardcoded constant. Update via UPDATE once verified; no migration needed either way.',
   'migration:010_app_config');

-- ============================================================
-- ROLLBACK: revert 010 (safe -- purely additive, nothing else reads this
-- table yet)
--
--   DROP TRIGGER IF EXISTS app_config_set_updated_at ON public.app_config;
--   DROP FUNCTION IF EXISTS public.app_config_touch_updated_at();
--   DROP TABLE IF EXISTS public.app_config;
-- ============================================================
