-- ============================================================
-- SS-028 — Multi-Provider AI Router & Gemini Styling Adapters
--
-- Per docs/tickets/SS-028-design.md §3.3/§4. Insert-only against the
-- app_config table 010_app_config.sql created — no DDL. Seeds the three
-- keys backend/services/ai_routing_specs.py's ConfigSpecs consume, with
-- values BYTE-IDENTICAL to those specs' coded defaults (checked by
-- backend/tests/test_ai_routing_specs.py -- delete this migration's rows
-- and behaviour is unchanged, per SS-026's own design guarantee).
--
-- Model IDs [VERIFIED 2026-07-30] against the real GEMINI_API_KEY /
-- ANTHROPIC_API_KEY and the installed google-genai==2.14.0 /
-- anthropic==0.116.0 SDKs -- see backend/services/ai_routing_specs.py's
-- module docstring and docs/worklog/SS-028.md's Developer entry for the
-- exact verification commands/output.
-- ============================================================

INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('ai_styling_routing_table',
   '{
     "version": 1,
     "default": {"provider": "gemini", "model": "gemini-2.5-flash-lite", "cost_class": "everyday", "reason": "default_everyday"},
     "rules": [
       {"when": {"tier": ["atelier"]}, "route": {"provider": "claude", "model": "claude-sonnet-5", "cost_class": "high_stakes", "reason": "tier_atelier"}},
       {"when": {"is_first_suggestion": true}, "route": {"provider": "claude", "model": "claude-sonnet-5", "cost_class": "high_stakes", "reason": "first_ever_suggestion"}},
       {"when": {"occasion": ["wedding_guest"]}, "route": {"provider": "claude", "model": "claude-sonnet-5", "cost_class": "high_stakes", "reason": "high_stakes_occasion"}},
       {"when": {"occasion_kind": ["ceremony", "festival"]}, "route": {"provider": "claude", "model": "claude-sonnet-5", "cost_class": "high_stakes", "reason": "high_stakes_occasion_kind"}}
     ],
     "failover": {"gemini": ["claude"], "claude": ["gemini"]}
   }'::jsonb, 'server',
   'AI styling provider/model routing table (SS-028). Rules evaluated in array order, first match wins; an update here changes routing with NO redeploy. version is informational only -- never branched on in code. gemini-2.5-flash-lite is live in this account''s model list but returned a 404 "no longer available to new users" on live verification 2026-07-30 -- shipped anyway (recorded B1 decision, docs/worklog/SS-028.md); GeminiStylingAdapter retries in-tier with gemini-3.1-flash-lite (EVERYDAY_FALLBACK_MODEL_ID, not a slot in this table) before the router fails over to claude. puja/religious/date_night/party deliberately stay on the everyday (gemini) route -- see B6.',
   'migration:011_seed_ai_routing_config'),
  ('ai_provider_quota',
   '{"gemini": {"rpm": 15, "tpm": 500000}, "claude": {"rpm": 50, "tpm": 30000}}'::jsonb, 'server',
   'Per-provider RPM/TPM ceilings for services/provider_quota.py::ProviderQuotaTracker (SS-028). Gemini''s ceiling here is a SHARE of the SAME account-wide pool gemini_quota_ceiling_rpm (tagging path, services/gemini_rate_limiter.py) also spends against -- apportioned by hand, not summed automatically or enforced jointly (BL-099). Both providers'' real paid-tier ceilings are unread-dashboard placeholders (BL-098); closing that needs a dashboard read and an UPDATE, no code change. A provider absent from this object is unlimited (no local gate) -- its own 429 then drives failover.',
   'migration:011_seed_ai_routing_config'),
  ('ai_router_policy',
   '{"attempt_timeout_seconds": 6.0, "total_deadline_seconds": 12.0, "parse_retry_attempts": 1, "expensive_share_alert_threshold": 0.30, "alert_min_sample": 20, "alert_cooldown_seconds": 3600, "provider_outage_alert_seconds": 900}'::jsonb, 'server',
   'services/styling_router.py::StylingRouter timing/alerting policy (SS-028). total_deadline_seconds (12s) is deliberately LARGER than SS-020''s "<4s cold call" AC -- that AC is happy-path-only (resolved B2, docs/worklog/SS-028.md); the failover/degrade path is allowed to exceed it. BL-100 tracks renegotiating SS-020''s AC text to say so explicitly. All seven fields are clamped in code -- a shape-valid but degenerate value here can never disable the router (see services/ai_routing_specs.py::RouterPolicyConfig).',
   'migration:011_seed_ai_routing_config');

-- ------------------------------------------------------------
-- 010_app_config.sql's gemini_quota_ceiling_rpm row is now ACTUALLY
-- consumed (routers/wardrobe.py::get_gemini_rate_limiter() applies it via
-- GeminiRateLimiter.set_max_requests() every request) -- its seed
-- description's "NOT YET CONSUMED" claim is now stale. Value unchanged
-- (still 15, still the pre-SS-028 conservative default -- no behaviour
-- regression); only the description is corrected.
-- ------------------------------------------------------------
UPDATE app_config
SET description = 'Provider quota ceiling for Gemini tagging calls (requests/minute). Consumed by routers/wardrobe.py::get_gemini_rate_limiter(), which applies this value onto the shared GeminiRateLimiter singleton via set_max_requests() every request (SS-028, closes BL-076). This is ONE of two independent in-process limiters spending the SAME Gemini account-wide quota pool -- see ai_provider_quota''s description and BL-099. Seeded conservative, matching the pre-SS-028 hardcoded default, pending BL-076''s/BL-098''s real paid-tier RPM verification. Update via UPDATE once verified; no migration needed either way.',
    updated_by = 'migration:011_seed_ai_routing_config'
WHERE key = 'gemini_quota_ceiling_rpm';

-- ============================================================
-- ROLLBACK: revert 011 (safe -- insert-only, plus one description-column
-- UPDATE on a pre-existing row; restores that row's 010 description
-- verbatim)
--
--   DELETE FROM app_config WHERE key IN (
--     'ai_styling_routing_table', 'ai_provider_quota', 'ai_router_policy'
--   );
--   UPDATE app_config
--   SET description = 'Provider quota ceiling for Gemini tagging calls (requests/minute). Seeded conservative, matching backend/services/gemini_rate_limiter.py''s current hardcoded default, pending BL-076''s real paid-tier RPM verification. NOT YET CONSUMED -- GeminiRateLimiter still reads its own hardcoded constant. Update via UPDATE once verified; no migration needed either way.',
--       updated_by = 'migration:010_app_config'
--   WHERE key = 'gemini_quota_ceiling_rpm';
-- ============================================================
