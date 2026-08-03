-- ============================================================
-- SS-029 — Cost & Capacity Ledger (`ai_cost_ledger`)
--
-- Per docs/tickets/SS-029-design.md §3.5, which named this file
-- `011_ai_cost_ledger.sql`. Renumbered to 012 by the Developer phase: the
-- shared live Supabase project (`mefpfykuinasgkpfhmzk`) already had a real
-- `011_*` migration applied from SS-027 (Styling Rules Engine, merged to
-- develop ahead of this branch -- see git log f29d0d5) by the time this
-- ticket's migration was pushed, confirmed via `supabase migration list
-- --linked` (remote shows version 011 applied) and a REST probe
-- (`colour_palette` table exists, `ai_cost_ledger` does not). Mechanical,
-- content-preserving rename only -- same collision class as this ticket
-- pair's BL-ID renumbering at Architect time. Every in-repo cross-reference
-- to this filename was updated to match (see docs/worklog/SS-029.md).
--
-- Per docs/tickets/SS-029-design.md §3.5. Forward-only: 001_initial.sql is
-- NEVER edited (BL-060). Purely additive.
--
-- One row per provider call, in exact integer micropaise
-- (1 rupee = 100 paise = 100_000_000 micropaise), attributed to a
-- request_id so retries/failovers stay truthful. Written exclusively by
-- backend/adapters/supabase_cost_ledger.py (service_role) -- never by a
-- client, and never via any other path.
-- ============================================================

-- ------------------------------------------------------------
-- Table
-- ------------------------------------------------------------

CREATE TABLE ai_cost_ledger (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  request_id      UUID NOT NULL,
  provider        TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_]*$'),
  model           TEXT NOT NULL,
  feature         TEXT NOT NULL CHECK (feature ~ '^[a-z][a-z0-9_]*$'),
  tokens_in       INTEGER CHECK (tokens_in  >= 0),   -- NULL for per_call providers
  tokens_out      INTEGER CHECK (tokens_out >= 0),
  -- cost_micropaise is the source of truth. cost_paise is a GENERATED
  -- column derived from it (never stored twice independently) -- the AC
  -- names cost_paise literally, but a plain INTEGER paise column would
  -- round a sub-paise-per-call cost (₹0.024 = 2.4 paise) to zero, silently
  -- under-reporting exactly the way the ticket forbids (design §3.1).
  -- BIGINT headroom: highest ceiling is ₹500/month = 5e10 micropaise,
  -- against an int64 max of ~9.2e18.
  cost_micropaise BIGINT NOT NULL DEFAULT 0 CHECK (cost_micropaise >= 0),
  cost_paise      NUMERIC(18,6) GENERATED ALWAYS AS (cost_micropaise::numeric / 1000000) STORED,
  latency_ms      INTEGER CHECK (latency_ms >= 0),
  cache_hit       BOOLEAN NOT NULL DEFAULT false,
  pricing_status  TEXT NOT NULL DEFAULT 'priced'
                    CHECK (pricing_status IN ('priced','estimated','unpriced')),
  price_effective_from DATE,                          -- NULL only when unpriced
  unit_price_snapshot  JSONB NOT NULL DEFAULT '{}',   -- exact rates + fx used, frozen at write time
  attempt         SMALLINT NOT NULL DEFAULT 1 CHECK (attempt >= 1),
  outcome         TEXT NOT NULL DEFAULT 'success'
                    CHECK (outcome IN ('success','failed','timeout','denied')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each tied to a named query, no speculative indexing.
CREATE INDEX idx_ai_cost_ledger_user_created ON ai_cost_ledger (user_id, created_at DESC);  -- per-user breakdown
CREATE INDEX idx_ai_cost_ledger_request      ON ai_cost_ledger (request_id);                -- per-request attribution
CREATE INDEX idx_ai_cost_ledger_feature      ON ai_cost_ledger (feature, created_at DESC);  -- per-feature breakdown

-- ------------------------------------------------------------
-- RLS — default-deny, service_role only. Follows 010_app_config.sql's
-- established shape: RLS enabled, and the ABSENCE of any policy is the
-- protection. DELIBERATELY no SELECT/INSERT/UPDATE/DELETE policy for
-- anon or authenticated -- service_role bypasses RLS; every other role
-- gets a hard deny. See design §3.5 for why this is required (not just
-- convenient): a user must not be able to DELETE their own spend rows and
-- erase the record the revenue gate depends on, and the write can outlive
-- the caller's short-lived JWT (BackgroundTasks callback).
-- ------------------------------------------------------------
ALTER TABLE ai_cost_ledger ENABLE ROW LEVEL SECURITY;
-- No policies -- intentional.

-- ------------------------------------------------------------
-- Breakdown view (satisfies "a per-user and per-feature cost breakdown is
-- queryable"). Grouping day is IST, matching the Redis counters.
-- unpriced_calls is its own column so a costing gap can never hide inside
-- a total that looks plausible.
-- ------------------------------------------------------------
CREATE VIEW ai_cost_breakdown AS
SELECT user_id,
       feature,
       provider,
       model,
       (created_at AT TIME ZONE 'Asia/Kolkata')::date AS ist_date,
       count(*)                                        AS call_count,
       count(*) FILTER (WHERE cache_hit)               AS cache_hits,
       count(*) FILTER (WHERE pricing_status = 'unpriced') AS unpriced_calls,
       sum(cost_micropaise) FILTER (WHERE pricing_status <> 'unpriced') AS cost_micropaise,
       sum(cost_paise)      FILTER (WHERE pricing_status <> 'unpriced') AS cost_paise
FROM ai_cost_ledger
GROUP BY user_id, feature, provider, model, ist_date;

-- ============================================================
-- ROLLBACK: revert 011 (safe -- purely additive, nothing else reads this
-- table/view yet)
--
--   DROP VIEW IF EXISTS public.ai_cost_breakdown;
--   DROP TABLE IF EXISTS public.ai_cost_ledger;
-- ============================================================
