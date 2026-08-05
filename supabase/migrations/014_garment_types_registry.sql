-- ============================================================
-- SS-034 -- Garment Types Registry (EXPAND phase only)
--
-- Per docs/tickets/SS-034-design.md. Purely additive: creates
-- garment_types / garment_type_aliases / garment_unknown_types / (BL-109
-- resolution) garment_set_components, then seeds the real Indian garment
-- vocabulary. Nothing in backend/ or mobile/ reads these tables yet --
-- enforced by backend/tests/test_garment_registry_purely_additive.py, not
-- merely claimed. wardrobe_items.category is untouched; MIGRATE/CONTRACT
-- are explicitly Wave 2, out of scope here.
--
-- Structurally lifted from 007_occasions_registry.sql (design §3.1-§3.4),
-- swapping `kind`/`badge_color`/`date_rule`/`tier_gate` (occasion-specific)
-- for `slot`/`layer` (garment physics) and adding garment_set_components
-- (design §3.7, the BL-109 resolution -- a type-level set-composition
-- primitive, NOT the item-level Wave 2 decision, which is untouched here).
-- ============================================================

-- ------------------------------------------------------------
-- Tables
-- ------------------------------------------------------------

-- Null semantics (design §3.1, copied verbatim from 007) -- the #1
-- silent-failure mode:
--   region_scope IS NULL  means UNIVERSAL / pan-India, NOT "no regions".
--   culture_scope IS NULL means the same.
-- The empty array is forbidden by CHECK precisely so nobody can write
-- "applies nowhere" and get a garment type that silently never matches.
-- Canonical applicability predicate, to be copied verbatim wherever
-- region/culture filtering ever happens:
--   (region_scope  IS NULL OR :user_region  = ANY(region_scope))
--   AND (culture_scope IS NULL OR :user_culture = ANY(culture_scope))
--
-- `slot`/`layer` are CLOSED structural sets -- physics, not fashion. Code
-- MAY switch on these. `register`/`coverage`/etc. are OPEN vocabulary --
-- data only, code NEVER switches on these (design §3.1).
--
-- Deviation from the proposal's §4 DDL sketch, flagged explicitly (design
-- §3.1): 'set' is a 12th `slot` value (proposal listed 11 -- needed for
-- BL-109's garment_set parent type, §3.7 below) and
-- CHECK (cardinality(register) > 0) is new (proposal declared
-- `register TEXT[] NOT NULL` but didn't forbid '{}', which would otherwise
-- be the same null-vs-empty-array hole 007 already guards against for
-- region_scope). Both are additive, zero-cost, reversible.
CREATE TABLE garment_types (
  key             TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  parent_key      TEXT REFERENCES garment_types(key) ON DELETE RESTRICT
                    CHECK (parent_key IS DISTINCT FROM key),
  label           TEXT NOT NULL,
  labels_i18n     JSONB NOT NULL DEFAULT '{}'::jsonb,

  -- CLOSED structural sets: physics, not fashion. Code MAY switch on these.
  slot            TEXT NOT NULL CHECK (slot IN (
                    'head','torso_base','torso_mid','legs','full_body',
                    'feet','neck','waist','wrist','carry','drape','set')),
  layer           SMALLINT NOT NULL CHECK (layer BETWEEN 0 AND 3),

  -- OPEN vocabulary: data only. Code NEVER switches on these.
  register        TEXT[] NOT NULL CHECK (cardinality(register) > 0),
  base_formality  SMALLINT NOT NULL CHECK (base_formality BETWEEN 0 AND 10),
  coverage        JSONB NOT NULL DEFAULT '{}'::jsonb,
  requires_with   TEXT[],
  pairs_with      TEXT[],
  excludes_with   TEXT[],
  region_scope    TEXT[] CHECK (region_scope  IS NULL OR cardinality(region_scope)  > 0),
  culture_scope   TEXT[] CHECK (culture_scope IS NULL OR cardinality(culture_scope) > 0),
  gender_affinity TEXT[],
  -- styling_rules JSONB shape (design §3.1, Architect judgment -- nothing
  -- reads this yet, no upstream spec pins a shape):
  --   { "volume_class": "fitted"|"relaxed"|"voluminous",  -- optional
  --     "length_yards": 6,                                -- saree children only
  --     "note": "free-text authoring rationale, not consumed by code" }
  -- All keys optional; absence means "no opinion," never "false." Wave 2 is
  -- free to redefine, extend, or ignore any key here.
  styling_rules   JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  sort_order      INTEGER NOT NULL DEFAULT 100,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- No GIN on any TEXT[] column: ~63 rows this ticket, low-hundreds at the
-- eventual 75-95-type ceiling -- sequential scan is correct (same reasoning
-- as 007). Revisit only if profiling says otherwise.
CREATE INDEX idx_garment_types_active_sort ON garment_types (is_active, sort_order);
CREATE INDEX idx_garment_types_parent      ON garment_types (parent_key);

-- `alias` and `garment_types.key` must be disjoint. Deliberately NOT
-- enforced by a constraint (Postgres has no cross-table CHECK) -- enforced
-- by RESOLUTION ORDER (canonical key wins before alias lookup, so a
-- collision is inert) plus an explicit test. Do not add a trigger.
CREATE TABLE garment_type_aliases (
  alias        TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  garment_key  TEXT NOT NULL REFERENCES garment_types(key) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_garment_type_aliases_key ON garment_type_aliases (garment_key);

-- Same durable-log role as 007's occasion_unknown_tags: store + log for
-- review rather than dropping the tag or failing the write. Covers every
-- future writer, not just the Gemini tagging path.
CREATE TABLE garment_unknown_types (
  slug           TEXT PRIMARY KEY,
  occurrences    INTEGER NOT NULL DEFAULT 1,
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_source  TEXT,   -- 'wardrobe_items' | future writers, per 007's precedent
  sample_user_id UUID
);

-- BL-109 resolution (design §3.7/§8): a type-level set-composition
-- primitive, landed NOW while zero garment_types rows exist anywhere yet
-- (the cheapest this retrofit will ever be). component_key may point at a
-- PARENT row (e.g. 'ethnic_bottom') to mean "any child of this parent
-- satisfies the slot" -- deliberate, resolved via parent_key by a future
-- consumer, same as styling_rules inheritance already works.
-- Item-level consumption (how a photographed wardrobe_items row maps onto
-- this) is explicitly NOT decided here -- see BL-116.
CREATE TABLE garment_set_components (
  set_key       TEXT NOT NULL REFERENCES garment_types(key) ON DELETE RESTRICT,
  component_key TEXT NOT NULL REFERENCES garment_types(key) ON DELETE RESTRICT,
  role          TEXT NOT NULL CHECK (role IN ('top','bottom','drape','layer','footwear')),
  is_required   BOOLEAN NOT NULL DEFAULT true,
  sort_order    INTEGER NOT NULL DEFAULT 100,
  PRIMARY KEY (set_key, component_key),
  CHECK (set_key IS DISTINCT FROM component_key)
);
CREATE INDEX idx_garment_set_components_set ON garment_set_components (set_key);

-- ------------------------------------------------------------
-- RLS -- mirrors 007's established pattern
--
-- DELIBERATELY no INSERT/UPDATE/DELETE policy on any of the four tables,
-- and no policy at all on garment_unknown_types. With RLS enabled and no
-- matching policy, writes from anon/authenticated are denied; service_role
-- bypasses RLS. ABSENCE OF A POLICY *IS* THE WRITE-PROTECTION MECHANISM --
-- do not "fix" this by adding a permissive write policy.
-- ------------------------------------------------------------
ALTER TABLE garment_types           ENABLE ROW LEVEL SECURITY;
ALTER TABLE garment_type_aliases    ENABLE ROW LEVEL SECURITY;
ALTER TABLE garment_unknown_types   ENABLE ROW LEVEL SECURITY;
ALTER TABLE garment_set_components  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_garment_types" ON garment_types
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_garment_type_aliases" ON garment_type_aliases
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_garment_set_components" ON garment_set_components
  FOR SELECT USING (auth.role() = 'authenticated');

-- ------------------------------------------------------------
-- Seed -- 8 parents + ~55 children = ~63 rows (design §3.5)
--
-- Defaults unless overridden per-row below: labels_i18n = '{}' (no
-- approved translations exist -- BL-090's root cause, not a new gap),
-- coverage = '{}', excludes_with = NULL, gender_affinity = NULL,
-- is_active = true, styling_rules = '{}' except where length_yards is
-- called out. layer convention: 0 = base garment (tops/bottoms/full-body/
-- sets), 2 = worn-over layering (drapes, jackets/coats); 1 and 3 reserved,
-- unused this ticket.
--
-- base_formality/register/coverage/styling_rules values not directly
-- sourced from the proposal's Appendix B are Architect judgment, flagged
-- for stylist review before any scoring code consumes them (design §3.5,
-- §9 open question 2). pairs_with/requires_with marked [VERIFIED - B.2] in
-- the design doc are transcribed verbatim from the proposal's sourced
-- table.
-- ------------------------------------------------------------

-- Parents (8 top-level rule sets -- design §3.5, "why 8 not ~15")
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, requires_with, pairs_with, styling_rules)
VALUES
  ('ethnic_top', NULL, 'Ethnic Top', 'torso_base', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['ethnic_bottom'], '{}'),
  ('ethnic_bottom', NULL, 'Ethnic Bottom', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['ethnic_top'], '{}'),
  ('modern_bottom', NULL, 'Modern Bottom', 'legs', 0,
    ARRAY['western','athleisure','streetwear'], 2, NULL, NULL, '{}'),
  ('drape', NULL, 'Drape', 'drape', 2,
    ARRAY['ethnic'], 5, NULL, NULL, '{}'),
  ('layering_jacket', NULL, 'Layering Jacket', 'torso_mid', 2,
    ARRAY['ethnic','indo_western'], 6, NULL, NULL, '{}'),
  ('saree', NULL, 'Saree', 'full_body', 0,
    ARRAY['ethnic'], 7, ARRAY['blouse','petticoat'], NULL, '{"length_yards": 6}'),
  ('full_body_garment', NULL, 'Full Body Garment', 'full_body', 0,
    ARRAY['ethnic','western','indo_western','resort'], 5, NULL, NULL, '{}'),
  ('garment_set', NULL, 'Garment Set', 'set', 0,
    ARRAY['ethnic'], 6, NULL, NULL, '{}');

-- Children of ethnic_top (8) -- no `kurti` row: length difference, not a
-- sibling type (B.1 finding #2; asserted by a negative test, design §6.1).
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, pairs_with, culture_scope)
VALUES
  ('kurta', 'ethnic_top', 'Kurta', 'torso_base', 0,
    ARRAY['ethnic','indo_western'], 4, ARRAY['ethnic_bottom','modern_bottom'], NULL),
  ('anarkali', 'ethnic_top', 'Anarkali', 'torso_base', 0,
    ARRAY['ethnic'], 7, NULL, NULL),
  ('angrakha', 'ethnic_top', 'Angrakha', 'torso_base', 0,
    ARRAY['ethnic'], 6, NULL, NULL),
  ('choli', 'ethnic_top', 'Choli', 'torso_base', 0,
    ARRAY['ethnic'], 7, ARRAY['lehenga_skirt','ghagra_chaniya'], NULL),
  ('blouse', 'ethnic_top', 'Blouse', 'torso_base', 0,
    ARRAY['ethnic'], 6, NULL, NULL),
  ('kameez', 'ethnic_top', 'Kameez', 'torso_base', 0,
    ARRAY['ethnic'], 4, ARRAY['salwar','churidar'], NULL),
  ('crop_top', 'ethnic_top', 'Crop Top', 'torso_base', 0,
    ARRAY['western','indo_western','streetwear'], 2, NULL, NULL),
  ('pathani', 'ethnic_top', 'Pathani', 'torso_base', 0,
    ARRAY['ethnic'], 5, NULL, ARRAY['muslim']);

-- Children of ethnic_bottom (17) -- the 10 B.2 [VERIFIED] ethnic bottoms
-- plus 7 regional/two-piece additions justified by the raw ticket's own
-- named edge cases (design §3.5).
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, requires_with, pairs_with, region_scope, culture_scope)
VALUES
  -- the 10 B.2 rows [VERIFIED]
  ('palazzo', 'ethnic_bottom', 'Palazzo', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurti','kurta','crop_top'], NULL, NULL),
  ('churidar', 'ethnic_bottom', 'Churidar', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurti','kurta'], NULL, NULL),
  ('sharara', 'ethnic_bottom', 'Sharara', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurti'], NULL, NULL),
  ('patiala_salwar', 'ethnic_bottom', 'Patiala Salwar', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurti','kurta'], NULL, NULL),
  ('gharara', 'ethnic_bottom', 'Gharara', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurti'], NULL, NULL),
  ('dhoti_pants', 'ethnic_bottom', 'Dhoti Pants', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurta'], NULL, NULL),
  ('cigarette_pants', 'ethnic_bottom', 'Cigarette Pants', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurti','kurta'], NULL, NULL),
  ('culottes', 'ethnic_bottom', 'Culottes', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurta'], NULL, NULL),
  ('leggings', 'ethnic_bottom', 'Leggings', 'legs', 0,
    ARRAY['ethnic','indo_western'], 4, NULL, ARRAY['kurta','kurti'], NULL, NULL),
  ('salwar', 'ethnic_bottom', 'Salwar', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kameez','kurta'], NULL, NULL),
  -- 7 regional/two-piece additions, beyond the literal 10
  ('mekhela', 'ethnic_bottom', 'Mekhela', 'legs', 0,
    ARRAY['ethnic'], 4, ARRAY['sador'], NULL, ARRAY['assam'], NULL),
  ('mundu', 'ethnic_bottom', 'Mundu', 'legs', 0,
    ARRAY['ethnic'], 4, ARRAY['neriyathu'], NULL, ARRAY['kerala'], NULL),
  ('dhoti', 'ethnic_bottom', 'Dhoti', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurta','pathani'], NULL, NULL),
  ('lungi', 'ethnic_bottom', 'Lungi', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurta'], NULL, NULL),
  ('veshti', 'ethnic_bottom', 'Veshti', 'legs', 0,
    ARRAY['ethnic'], 4, NULL, ARRAY['kurta'], ARRAY['tamil_nadu'], NULL),
  ('ghagra_chaniya', 'ethnic_bottom', 'Ghagra Chaniya', 'legs', 0,
    ARRAY['ethnic'], 8, NULL, ARRAY['choli'], ARRAY['rajasthan','gujarat'], NULL),
  ('lehenga_skirt', 'ethnic_bottom', 'Lehenga Skirt', 'legs', 0,
    ARRAY['ethnic'], 8, NULL, ARRAY['choli','blouse'], NULL, NULL);

-- Children of modern_bottom (3) -- the ticket's own "genuinely-missing
-- modern types," bottom half.
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality)
VALUES
  ('cargo_pants', 'modern_bottom', 'Cargo Pants', 'legs', 0,
    ARRAY['western','athleisure','streetwear'], 1),
  ('joggers', 'modern_bottom', 'Joggers', 'legs', 0,
    ARRAY['western','athleisure','streetwear'], 1),
  ('dungarees', 'modern_bottom', 'Dungarees', 'legs', 0,
    ARRAY['western','athleisure','streetwear'], 2);

-- Children of drape (7)
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, requires_with, region_scope)
VALUES
  ('dupatta', 'drape', 'Dupatta', 'drape', 2, ARRAY['ethnic'], 5, NULL, NULL),
  ('stole', 'drape', 'Stole', 'drape', 2, ARRAY['ethnic'], 5, NULL, NULL),
  ('shawl', 'drape', 'Shawl', 'drape', 2, ARRAY['ethnic'], 5, NULL, NULL),
  ('odhni', 'drape', 'Odhni', 'drape', 2, ARRAY['ethnic'], 5, NULL, NULL),
  ('phulkari_dupatta', 'drape', 'Phulkari Dupatta', 'drape', 2, ARRAY['ethnic'], 7, NULL, ARRAY['punjab']),
  ('sador', 'drape', 'Sador', 'drape', 2, ARRAY['ethnic'], 5, ARRAY['mekhela'], ARRAY['assam']),
  ('neriyathu', 'drape', 'Neriyathu', 'drape', 2, ARRAY['ethnic'], 5, ARRAY['mundu'], ARRAY['kerala']);

-- Children of layering_jacket (5 -- exactly the ticket's named list)
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality)
VALUES
  ('nehru_jacket', 'layering_jacket', 'Nehru Jacket', 'torso_mid', 2, ARRAY['ethnic','indo_western'], 6),
  ('waistcoat', 'layering_jacket', 'Waistcoat', 'torso_mid', 2, ARRAY['ethnic','indo_western'], 6),
  ('blazer', 'layering_jacket', 'Blazer', 'torso_mid', 2, ARRAY['ethnic','indo_western','western'], 6),
  ('shrug', 'layering_jacket', 'Shrug', 'torso_mid', 2, ARRAY['ethnic','indo_western'], 6),
  ('koti', 'layering_jacket', 'Koti', 'torso_mid', 2, ARRAY['ethnic','indo_western'], 6);

-- Children of saree (3) -- 9-yard vs 6-yard drapes cannot be modelled as
-- one row (B.1 finding #3); kanjeevaram flagged for Wave 2's
-- attribute-vs-type review (design §3.5/§7 edge case 12).
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, region_scope, culture_scope, styling_rules)
VALUES
  ('nauvari', 'saree', 'Nauvari', 'full_body', 0, ARRAY['ethnic'], 7,
    ARRAY['maharashtra'], NULL, '{"length_yards": 9}'),
  ('madisar', 'saree', 'Madisar', 'full_body', 0, ARRAY['ethnic'], 7,
    ARRAY['tamil_nadu'], ARRAY['tamil_brahmin'], '{"length_yards": 9}'),
  ('kanjeevaram', 'saree', 'Kanjeevaram', 'full_body', 0, ARRAY['ethnic'], 7,
    ARRAY['tamil_nadu'], NULL, '{"length_yards": 6}');

-- Children of full_body_garment (4)
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, region_scope)
VALUES
  ('sherwani', 'full_body_garment', 'Sherwani', 'full_body', 2, ARRAY['ethnic'], 8, NULL),
  ('kaftan', 'full_body_garment', 'Kaftan', 'full_body', 0,
    ARRAY['ethnic','western','indo_western','resort'], 3, NULL),
  ('jumpsuit', 'full_body_garment', 'Jumpsuit', 'full_body', 0,
    ARRAY['western','athleisure','streetwear'], 3, NULL),
  ('phiran', 'full_body_garment', 'Phiran', 'full_body', 0, ARRAY['ethnic'], 4, ARRAY['kashmir']);

-- Children of garment_set (8) -- BL-109 resolution: B.3's 8 canonical
-- women's forms, saree swapped for co_ord_set (design §3.7/§8 -- a saree's
-- own requires_with already covers its bundle case without a redundant
-- row).
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality)
VALUES
  ('kurta_set', 'garment_set', 'Kurta Set', 'set', 0, ARRAY['ethnic'], 5),
  ('salwar_kameez_set', 'garment_set', 'Salwar Kameez Set', 'set', 0, ARRAY['ethnic'], 5),
  ('anarkali_set', 'garment_set', 'Anarkali Set', 'set', 0, ARRAY['ethnic'], 7),
  ('sharara_set', 'garment_set', 'Sharara Set', 'set', 0, ARRAY['ethnic'], 8),
  ('gharara_set', 'garment_set', 'Gharara Set', 'set', 0, ARRAY['ethnic'], 8),
  ('lehenga_choli_set', 'garment_set', 'Lehenga Choli Set', 'set', 0, ARRAY['ethnic'], 9),
  ('half_saree_set', 'garment_set', 'Half Saree Set', 'set', 0, ARRAY['ethnic'], 8),
  ('co_ord_set', 'garment_set', 'Co-ord Set', 'set', 0, ARRAY['western','athleisure','streetwear'], 3);

-- ------------------------------------------------------------
-- garment_type_aliases seed (design §3.6, representative not exhaustive --
-- same posture as 007's 8 for 12 occasions). Each alias is already
-- shape-normalised (regex CHECK requires it) -- e.g. "co-ord" is stored as
-- "co_ord" since the hyphen would fail the CHECK and would also already
-- shape-normalise to that form at lookup time. "crop_top" is intentionally
-- NOT stored as an alias of itself -- "crop-top" shape-normalises straight
-- to the canonical key "crop_top" with no alias needed, and storing it
-- would break the alias/key disjointness test.
-- ------------------------------------------------------------
INSERT INTO garment_type_aliases (alias, garment_key) VALUES
  ('plazo', 'palazzo'),
  ('palazzos', 'palazzo'),
  ('churidaar', 'churidar'),
  ('churidars', 'churidar'),
  ('shalwar', 'salwar'),
  ('salwaar', 'salwar'),
  ('patiala', 'patiala_salwar'),
  ('patiyala', 'patiala_salwar'),
  ('ghararah', 'gharara'),
  ('shararaa', 'sharara'),
  ('dhoti_pant', 'dhoti_pants'),
  ('cigarette_pant', 'cigarette_pants'),
  ('cigarette_trousers', 'cigarette_pants'),
  ('culotte', 'culottes'),
  ('legging', 'leggings'),
  ('dupattas', 'dupatta'),
  ('dupata', 'dupatta'),
  ('nehrujacket', 'nehru_jacket'),
  ('nehru_coat', 'nehru_jacket'),
  ('croptop', 'crop_top'),
  ('kurta_suit', 'kurta_set'),
  ('punjabi_suit', 'salwar_kameez_set'),
  ('coord_set', 'co_ord_set'),
  ('co_ord', 'co_ord_set');

-- ------------------------------------------------------------
-- garment_set_components seed (design §3.7) -- ~20 rows, 7 sets of 3
-- (top/bottom/drape) plus co_ord_set's 2 (top/bottom, no drape). role
-- values are illustrative of the CHECK's vocabulary, not a fixed 1:1 to
-- `slot` -- this table's job is "what fills this bundle," not "what body
-- part this occupies" (still garment_types.slot, unchanged).
-- ------------------------------------------------------------
INSERT INTO garment_set_components (set_key, component_key, role, is_required, sort_order) VALUES
  ('kurta_set', 'kurta', 'top', true, 10),
  ('kurta_set', 'ethnic_bottom', 'bottom', true, 20),
  ('kurta_set', 'dupatta', 'drape', false, 30),

  ('salwar_kameez_set', 'kameez', 'top', true, 10),
  ('salwar_kameez_set', 'salwar', 'bottom', true, 20),
  ('salwar_kameez_set', 'dupatta', 'drape', true, 30),

  ('anarkali_set', 'anarkali', 'top', true, 10),
  ('anarkali_set', 'churidar', 'bottom', true, 20),
  ('anarkali_set', 'dupatta', 'drape', false, 30),

  ('sharara_set', 'kurta', 'top', true, 10),
  ('sharara_set', 'sharara', 'bottom', true, 20),
  ('sharara_set', 'dupatta', 'drape', true, 30),

  ('gharara_set', 'kurta', 'top', true, 10),
  ('gharara_set', 'gharara', 'bottom', true, 20),
  ('gharara_set', 'dupatta', 'drape', true, 30),

  ('lehenga_choli_set', 'choli', 'top', true, 10),
  ('lehenga_choli_set', 'lehenga_skirt', 'bottom', true, 20),
  ('lehenga_choli_set', 'dupatta', 'drape', true, 30),

  -- approximation, flagged in the design (§3.7/§7 edge case 11): a
  -- half-saree's upper drape ("oni"/langa-voni) is larger/differently
  -- draped than a standard dupatta; not fixed here.
  ('half_saree_set', 'blouse', 'top', true, 10),
  ('half_saree_set', 'lehenga_skirt', 'bottom', true, 20),
  ('half_saree_set', 'dupatta', 'drape', true, 30),

  ('co_ord_set', 'crop_top', 'top', true, 10),
  ('co_ord_set', 'modern_bottom', 'bottom', true, 20);

-- ------------------------------------------------------------
-- Normalisation + logging functions (design §3.3) -- same four-function
-- contract as 007, renamed, SCALAR ONLY (no garment_normalize_array --
-- wardrobe_items.category is a single value today, not an array like
-- occasion_tags; adding an array wrapper later is the same cheap, proven
-- pattern if Wave 2 ever needs it).
--
-- Contract, identical in spirit to 007's:
--   1. trim -> lower -> collapse runs of whitespace and '-' to a single
--      '_' -> strip any character outside [a-z0-9_]
--   2. if the result matches garment_types.key        -> use it
--   3. else if it matches garment_type_aliases.alias   -> use garment_key
--   4. else -> KEEP the normalised string as-is and record it in
--      garment_unknown_types. Never drop it. Never fail the write.
-- Step 2 before step 3 is what makes an alias/key collision inert.
--
-- All SECURITY DEFINER (except the shape-only step, which touches no
-- table) with SET search_path = public, pg_temp. Nothing calls these
-- functions in this ticket; they exist inert, exactly as 007's did before
-- 008 wired a trigger.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.garment_normalize_shape(p_raw TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
  SELECT NULLIF(
    regexp_replace(
      regexp_replace(lower(btrim(p_raw)), '[[:space:]-]+', '_', 'g'),
      '[^a-z0-9_]', '', 'g'
    ),
    ''
  );
$$;

COMMENT ON FUNCTION public.garment_normalize_shape(TEXT) IS
  'SS-034 step 1 of the garment normalisation contract: trim/lower/collapse to underscore/strip. Returns NULL for NULL or an all-punctuation input.';

CREATE OR REPLACE FUNCTION public.garment_normalize_one(p_raw TEXT)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_shaped TEXT;
  v_mapped TEXT;
BEGIN
  IF p_raw IS NULL THEN
    RETURN NULL;
  END IF;

  v_shaped := public.garment_normalize_shape(p_raw);
  IF v_shaped IS NULL THEN
    RETURN NULL;
  END IF;

  -- Step 2 -- canonical key wins FIRST. This ordering is what makes an
  -- alias/key collision inert (design §3.3).
  IF EXISTS (SELECT 1 FROM public.garment_types g WHERE g.key = v_shaped) THEN
    RETURN v_shaped;
  END IF;

  -- Step 3 -- alias lookup.
  SELECT a.garment_key INTO v_mapped
  FROM public.garment_type_aliases a
  WHERE a.alias = v_shaped;

  IF v_mapped IS NOT NULL THEN
    RETURN v_mapped;
  END IF;

  -- Step 4 -- unknown: keep the normalised string AND flag it. Unlike
  -- 007's occasion_normalize_one (which leaves logging to the array
  -- wrapper), this ticket ships no array variant (design §3.3), so the
  -- scalar function itself is the only place a future single-value caller
  -- (e.g. a wardrobe_items trigger) will ever go through -- it must log
  -- here or an unknown garment slug would silently never be captured.
  -- No caller context (source/user) is available at this call site, so
  -- both are logged NULL; garment_log_unknown remains directly callable
  -- with real context from any future writer that has it.
  PERFORM public.garment_log_unknown(v_shaped, NULL, NULL);
  RETURN v_shaped;
END;
$$;

CREATE OR REPLACE FUNCTION public.garment_is_known(p_slug TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT EXISTS (SELECT 1 FROM public.garment_types g WHERE g.key = p_slug);
$$;

CREATE OR REPLACE FUNCTION public.garment_log_unknown(
  p_slug TEXT,
  p_src  TEXT,
  p_uid  UUID
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_slug IS NULL THEN
    RETURN;
  END IF;
  -- Single atomic INSERT ... ON CONFLICT DO UPDATE -- deliberately NOT a
  -- read-then-write (BL-066/BL-036: this ticket adds no third instance of
  -- that bug class).
  INSERT INTO public.garment_unknown_types (slug, sample_source, sample_user_id)
  VALUES (p_slug, p_src, p_uid)
  ON CONFLICT (slug) DO UPDATE
    SET occurrences  = garment_unknown_types.occurrences + 1,
        last_seen_at = now();
END;
$$;

-- ============================================================
-- ROLLBACK: revert 014 (safe -- nothing reads these yet)
--
--   DROP FUNCTION IF EXISTS public.garment_log_unknown(TEXT, TEXT, UUID);
--   DROP FUNCTION IF EXISTS public.garment_is_known(TEXT);
--   DROP FUNCTION IF EXISTS public.garment_normalize_one(TEXT);
--   DROP FUNCTION IF EXISTS public.garment_normalize_shape(TEXT);
--   DROP TABLE IF EXISTS public.garment_set_components;
--   DROP TABLE IF EXISTS public.garment_unknown_types;
--   DROP TABLE IF EXISTS public.garment_type_aliases;
--   DROP TABLE IF EXISTS public.garment_types;
-- ============================================================
