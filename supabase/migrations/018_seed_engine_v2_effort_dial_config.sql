-- ============================================================
-- SS-039 -- Engine v2 effort dial (E0/E1/E2) config seed
--
-- Per docs/tickets/SS-039-design.md. Data-only: ONE INSERT into the
-- already-live app_config table (010_app_config.sql) -- no DDL, no ALTER,
-- no CREATE. Values transcribed VERBATIM from the raw ticket's own E0-E2
-- table (docs/tickets/raw/SS-039.md); the coded default in
-- backend/services/app_config_specs.py::EngineV2EffortTierConfig matches
-- this row exactly, so a missing/malformed row degrades to this same
-- documented floor, not silently below it (AC #2).
--
-- No live consumer wires the resolved tier into engine_v2_candidate_search
-- / engine_v2_portfolio yet -- backend/services/engine_v2_effort_dial.py's
-- resolve_effort_tier_for_request() reads this row, but SS-020 owns wiring
-- a real caller. This row is therefore inert (no blast radius) until then.
-- ============================================================

INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('engine_v2_effort_tiers',
   '{
     "e0": {"search_pool_size": 500, "colour_mode": "star", "mmr_lambda": 0.9, "max_exploration": 0, "llm_candidate_count": null},
     "e1": {"search_pool_size": 1500, "colour_mode": "pairwise", "mmr_lambda": 0.85, "max_exploration": 0, "llm_candidate_count": 5},
     "e2": {"search_pool_size": 5000, "colour_mode": "pairwise_plus_volume", "mmr_lambda": 0.75, "max_exploration": 1, "llm_candidate_count": 6}
   }'::jsonb,
   'server',
   'Engine v2 effort dial (SS-039) -- E0 (degraded)/E1 (economy)/E2 (standard) tier parameters: search pool size, colour mode (documentation-only today, BL-135), MMR lambda/exploration-slot count, LLM candidate count. Resolved per-request by backend/services/engine_v2_effort_dial.py::resolve_effort_tier_for_request() from SS-028''s RoutingMixMonitor (provider health) and SS-029''s CostBudgetGate (budget status) -- not yet wired to a live caller (SS-020''s job). Coded default in app_config_specs.py::EngineV2EffortTierConfig matches this row exactly; a missing or malformed row degrades to that same documented floor. E3/E4 are structurally out of scope (docs/tickets/raw/SS-039.md) -- this schema is additive-only for a future ticket to add them.',
   'migration:018_seed_engine_v2_effort_dial_config');

-- ============================================================
-- ROLLBACK: revert 018 (safe -- a missing row degrades to the exact same
-- coded default, by design; see AppConfigService.read())
--
--   DELETE FROM app_config WHERE key = 'engine_v2_effort_tiers';
-- ============================================================
