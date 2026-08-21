-- ============================================================
-- SS-040 -- Item Lifecycle & Cost-Per-Wear Schema (trimmed)
--
-- Per docs/tickets/SS-040-design.md. Adds the five wardrobe_items columns
-- that genuinely do not exist yet (do_not_style, is_archived, condition,
-- custom_tags, render_transform). Purely additive: no existing column
-- type-changed, nothing dropped, no data rewritten (Postgres 11+ implements
-- `ADD COLUMN ... NOT NULL DEFAULT <constant>` as a metadata-only fast
-- default, [trained-knowledge, not verified this session]).
--
-- do_not_style/is_archived are wired into engine_v2_eligibility.filter_eligible
-- in this same ticket -- see backend/services/engine_v2_eligibility.py.
-- condition/custom_tags/render_transform ship as columns with no consumer
-- yet (BL-194/BL-195/BL-196 record the gaps; SS-052/SS-055/SS-048 are the
-- future readers/writers).
--
-- RLS: NO POLICY CHANGE. RLS is row-level (user_owns_wardrobe ON
-- wardrobe_items FOR ALL USING (auth.uid() = user_id), 001_initial.sql:164-
-- 165) -- new columns on an existing row are already covered by that
-- policy.
--
-- Booleans ship NOT NULL DEFAULT false (not bare nullable): a NULL boolean
-- reaching backend/services/styling_rules_types.WardrobeItemInput would fail
-- pydantic validation, and outfit_portfolio_service._fetch_wardrobe silently
-- DROPS any row that fails validation -- removing the possibility at the
-- column is safer than catching it downstream.
--
-- Apply via: supabase db push (linked project).
-- ============================================================

ALTER TABLE wardrobe_items
  ADD COLUMN IF NOT EXISTS do_not_style     BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_archived      BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS condition        TEXT,
  ADD COLUMN IF NOT EXISTS custom_tags      TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS render_transform JSONB;

-- Mirrors 001_initial.sql:77's idx_wardrobe_occasions ON wardrobe_items
-- USING GIN(occasion_tags).
CREATE INDEX IF NOT EXISTS idx_wardrobe_custom_tags
  ON wardrobe_items USING GIN(custom_tags);

COMMENT ON COLUMN wardrobe_items.do_not_style IS
  'SS-040. Read by backend/services/engine_v2_eligibility.filter_eligible -- excluded from the eligible pool, never relaxed by the SS-022 weather guardrail. No writer exists yet (BL-194).';
COMMENT ON COLUMN wardrobe_items.is_archived IS
  'SS-040. Read by backend/services/engine_v2_eligibility.filter_eligible -- excluded from the eligible pool, never relaxed by the SS-022 weather guardrail. No writer exists yet (BL-194).';
COMMENT ON COLUMN wardrobe_items.render_transform IS
  'SS-040. Nullable JSONB, no shape enforced here -- SS-055 owns the {x, y, scale, rotation, z} shape and its readers. Purely additive placeholder until then (see test_render_transform_purely_additive.py).';

-- ============================================================
-- ROLLBACK: revert 023 (safe -- additive-only, no existing column altered,
-- no data rewritten by ADD COLUMN ... DEFAULT on PG11+).
--
--   DROP INDEX IF EXISTS idx_wardrobe_custom_tags;
--   ALTER TABLE wardrobe_items
--     DROP COLUMN IF EXISTS render_transform,
--     DROP COLUMN IF EXISTS custom_tags,
--     DROP COLUMN IF EXISTS condition,
--     DROP COLUMN IF EXISTS is_archived,
--     DROP COLUMN IF EXISTS do_not_style;
-- ============================================================
