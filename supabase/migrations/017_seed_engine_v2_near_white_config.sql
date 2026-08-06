-- ============================================================
-- SS-038 -- Engine v2 near-white threshold config seed
--
-- Per docs/tickets/SS-038-design.md. Data-only: ONE INSERT into the
-- already-live app_config table (010_app_config.sql) -- no DDL, no ALTER,
-- no CREATE. Coded default IDENTICAL to today's
-- NEAR_WHITE_VALUE_THRESHOLD=0.92/NEAR_WHITE_SATURATION_THRESHOLD=0.12
-- constants (SS-026's "missing/malformed row behaves exactly like today"
-- pattern, same as 011's ai_styling_routing_table seed) -- resolves
-- BL-111 by making the threshold tunable without a code change or
-- redeploy, per the user's 2026-08-06 sign-off (keep the aggressive
-- default, do not narrow it).
-- ============================================================

INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('near_white_threshold',
   '{"value_threshold": 0.92, "saturation_threshold": 0.12}'::jsonb,
   'server',
   'HSV near-white/cream/ivory exclusion thresholds for occasion colour eligibility (Engine v2 stage 1). Coded default identical to SS-027/037''s original NEAR_WHITE_VALUE_THRESHOLD/NEAR_WHITE_SATURATION_THRESHOLD constants -- resolves BL-111 by making the threshold tunable without a code change or redeploy. Overridable per-occasion via occasions.styling_rules.near_white_value_threshold / near_white_saturation_threshold (StylingRulesOverride schema, services/styling_rules_types.py). A missing or malformed row degrades to these exact coded defaults.',
   'migration:017_seed_engine_v2_near_white_config');

-- ============================================================
-- ROLLBACK: revert 017 (safe -- a missing row degrades to the exact same
-- coded default, by design; see AppConfigService.read())
--
--   DELETE FROM app_config WHERE key = 'near_white_threshold';
-- ============================================================
