-- ============================================================
-- SS-044 -- Indian Garment Types & Category Migration (MIGRATE phase,
-- resolves BL-132, closes BL-156).
--
-- Per docs/tickets/SS-044-design.md. Approach (a) -- alias rows, NOT an
-- ENUM->TEXT column migration (design's "Migration approach" section
-- records the full reasoning for rejecting (b)). Purely additive: no
-- existing wardrobe_items row is touched, no column type changes, no
-- DROP of anything. `garment_registry_adapter.get_garment_attributes`
-- already resolves through `garment_type_aliases` with ZERO code change
-- (verified against services/garment_registry_adapter.py:107-121) -- this
-- migration is pure data.
--
-- Three ordered parts, all additive:
--   (1) new garment_types rows -- 13 bucket rows (aliased directly by the
--       21-value wardrobe_category enum) + 9 fine-grained `feet`-slot
--       children (BL-156's real content, not aliased today).
--   (2) styling_rules.volume_class backfill on every existing 014 row
--       (design finding 4 / BL-191 -- the hidden second blocker: without
--       this, volume_balance_score stays inert even after a perfect
--       category->registry mapping, because it skips any pair missing
--       volume_class).
--   (3) 21 garment_type_aliases rows, one per wardrobe_category enum
--       value (supabase/migrations/001_initial.sql:7-14, transcribed
--       verbatim).
--
-- Every base_formality/register/volume_class value below is Architect
-- judgment, not verified stylist input -- same posture as 014's own seed
-- comment, folds into BL-193/BL-077's unrun eval. Not presented as
-- sourced.
-- ============================================================

-- ------------------------------------------------------------
-- Part (1a) -- 13 bucket rows, aliased directly by the enum.
-- Column order follows 014's inserts. layer: 0 = base garment,
-- 2 = worn-over (design §"New garment_types rows").
-- ------------------------------------------------------------
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, styling_rules)
VALUES
  ('modern_top', NULL, 'Modern Top', 'torso_base', 0,
    ARRAY['western','athleisure','streetwear'], 2, '{"volume_class":"fitted"}'),
  ('dress', 'full_body_garment', 'Dress', 'full_body', 0,
    ARRAY['western','resort'], 5, '{"volume_class":"relaxed"}'),
  ('modern_outerwear', NULL, 'Modern Outerwear', 'torso_mid', 2,
    ARRAY['western','streetwear'], 4, '{"volume_class":"relaxed"}'),
  ('indo_western_outfit', 'full_body_garment', 'Indo-Western Outfit', 'full_body', 0,
    ARRAY['indo_western'], 5, '{"volume_class":"relaxed"}'),
  ('formal_footwear', NULL, 'Formal Footwear', 'feet', 0,
    ARRAY['western','indo_western'], 7, '{"volume_class":"fitted"}'),
  ('casual_footwear', NULL, 'Casual Footwear', 'feet', 0,
    ARRAY['western','athleisure','streetwear'], 3, '{"volume_class":"fitted"}'),
  ('ethnic_footwear', NULL, 'Ethnic Footwear', 'feet', 0,
    ARRAY['ethnic','indo_western'], 6, '{"volume_class":"fitted"}'),
  ('sports_footwear', NULL, 'Sports Footwear', 'feet', 0,
    ARRAY['athleisure','streetwear'], 1, '{"volume_class":"fitted"}'),
  -- The four accessory buckets carry deliberately BROAD register arrays --
  -- a watch or a bag is register-neutral in practice, and a narrow array
  -- would make register_coherence_score invent a 0.5 penalty for pairing
  -- a watch with a kurta. Breadth here is the conservative "no opinion"
  -- (1.0) choice, not a fabricated penalty. scarf is deliberately
  -- western-register -- dupatta/stole is the ethnic drape and already
  -- exists (design §1).
  ('bag', NULL, 'Bag', 'carry', 0,
    ARRAY['western','ethnic','indo_western','streetwear'], 4, '{"volume_class":"fitted"}'),
  ('jewellery', NULL, 'Jewellery', 'neck', 0,
    ARRAY['ethnic','indo_western','western'], 5, '{"volume_class":"fitted"}'),
  ('watch', NULL, 'Watch', 'wrist', 0,
    ARRAY['western','indo_western','athleisure'], 4, '{"volume_class":"fitted"}'),
  ('belt', NULL, 'Belt', 'waist', 0,
    ARRAY['western','indo_western','streetwear'], 3, '{"volume_class":"fitted"}'),
  ('scarf', NULL, 'Scarf', 'drape', 2,
    ARRAY['western','indo_western'], 3, '{"volume_class":"relaxed"}');

-- ------------------------------------------------------------
-- Part (1b) -- 9 fine-grained `feet` children (BL-156's real content, not
-- plumbing). No alias points at these today -- seeded for a future finer
-- tagger / preferred_footwear_categories work. All slot='feet', layer=0,
-- volume_class='fitted'. region_scope reuses 014's exact existing strings
-- (punjab/rajasthan/maharashtra) -- BL-117 consumed, not fixed.
-- ------------------------------------------------------------
INSERT INTO garment_types
  (key, parent_key, label, slot, layer, register, base_formality, region_scope, styling_rules)
VALUES
  ('jutti', 'ethnic_footwear', 'Jutti', 'feet', 0,
    ARRAY['ethnic'], 6, ARRAY['punjab','rajasthan'], '{"volume_class":"fitted"}'),
  ('mojari', 'ethnic_footwear', 'Mojari', 'feet', 0,
    ARRAY['ethnic'], 6, ARRAY['rajasthan'], '{"volume_class":"fitted"}'),
  ('kolhapuri', 'ethnic_footwear', 'Kolhapuri', 'feet', 0,
    ARRAY['ethnic','indo_western'], 5, ARRAY['maharashtra'], '{"volume_class":"fitted"}'),
  ('chappal', 'casual_footwear', 'Chappal', 'feet', 0,
    ARRAY['ethnic','western','streetwear'], 2, NULL, '{"volume_class":"fitted"}'),
  ('sandal', 'casual_footwear', 'Sandal', 'feet', 0,
    ARRAY['western','resort','streetwear'], 3, NULL, '{"volume_class":"fitted"}'),
  ('sneaker', 'casual_footwear', 'Sneaker', 'feet', 0,
    ARRAY['western','athleisure','streetwear'], 2, NULL, '{"volume_class":"fitted"}'),
  ('loafer', 'formal_footwear', 'Loafer', 'feet', 0,
    ARRAY['western','indo_western'], 6, NULL, '{"volume_class":"fitted"}'),
  ('oxford', 'formal_footwear', 'Oxford', 'feet', 0,
    ARRAY['western'], 8, NULL, '{"volume_class":"fitted"}'),
  ('heel', 'formal_footwear', 'Heel', 'feet', 0,
    ARRAY['western','indo_western'], 7, NULL, '{"volume_class":"fitted"}');

-- ------------------------------------------------------------
-- Part (2) -- volume_class backfill on every existing 014 row (design §3 /
-- finding 4 / BL-191 -- AC #3's real unblocker). Written as a jsonb ||
-- merge so saree/nauvari/madisar/kanjeevaram's existing length_yards key
-- survives (_to_garment_attributes reads only styling_rules.volume_class
-- and ignores everything else -- the merge is safe).
--
-- Allowed values are exactly 014's documented three: fitted | relaxed |
-- voluminous. _VOLUMINOUS_CLASSES in engine_v2_attribute_scoring.py:68 is
-- {"voluminous", "oversized"} -- use "voluminous", not "oversized"; the
-- latter is accepted by the scorer but is not in 014's documented
-- vocabulary.
--
-- Coverage rule: after this part, EVERY row in garment_types has a
-- volume_class -- asserted by T4/T10, not by eye. Parent rows are
-- included below because they are alias targets too (western_bottom ->
-- modern_bottom), so leaving them unset would silently re-inert the
-- signal for those categories.
-- ------------------------------------------------------------

-- voluminous
UPDATE garment_types
SET styling_rules = styling_rules || '{"volume_class":"voluminous"}'::jsonb
WHERE key IN (
  'anarkali', 'sharara', 'gharara', 'ghagra_chaniya', 'lehenga_skirt',
  'lehenga_choli_set', 'sharara_set', 'gharara_set', 'anarkali_set',
  'half_saree_set', 'palazzo', 'patiala_salwar', 'culottes', 'dhoti_pants',
  'kaftan', 'phiran'
);

-- relaxed -- includes all `drape` children and all `layering_jacket`
-- children (resolved via their parent_key, not enumerated by hand, so a
-- future child of either parent inherits the same default rather than
-- silently landing with volume_class unset).
UPDATE garment_types
SET styling_rules = styling_rules || '{"volume_class":"relaxed"}'::jsonb
WHERE key IN (
  'kurta', 'kameez', 'angrakha', 'pathani', 'salwar', 'mundu', 'mekhela',
  'dhoti', 'lungi', 'veshti', 'sherwani', 'jumpsuit', 'co_ord_set',
  'kurta_set', 'salwar_kameez_set', 'cargo_pants', 'joggers', 'dungarees',
  'saree', 'nauvari', 'madisar', 'kanjeevaram'
)
OR parent_key IN ('drape', 'layering_jacket');

-- fitted
UPDATE garment_types
SET styling_rules = styling_rules || '{"volume_class":"fitted"}'::jsonb
WHERE key IN ('churidar', 'cigarette_pants', 'leggings', 'choli', 'blouse', 'crop_top');

-- Parent rows (design §3): 'relaxed' -- alias targets too
-- (western_bottom -> modern_bottom), so leaving them unset would silently
-- re-inert the signal for those categories.
UPDATE garment_types
SET styling_rules = styling_rules || '{"volume_class":"relaxed"}'::jsonb
WHERE key IN (
  'ethnic_top', 'ethnic_bottom', 'modern_bottom', 'drape', 'layering_jacket',
  'full_body_garment', 'garment_set'
);

-- ------------------------------------------------------------
-- Part (3) -- 21 garment_type_aliases rows, one per live wardrobe_category
-- enum value (001_initial.sql:7-14, transcribed verbatim). See design §1
-- for the two judgment-call mappings (ethnic_lehenga ->
-- lehenga_choli_set; western_outerwear -> modern_outerwear, NOT
-- layering_jacket, to avoid register_coherence_score reporting false
-- coherence with ethnic items).
-- ------------------------------------------------------------
INSERT INTO garment_type_aliases (alias, garment_key) VALUES
  ('western_top', 'modern_top'),
  ('western_bottom', 'modern_bottom'),
  ('western_dress', 'dress'),
  ('western_outerwear', 'modern_outerwear'),
  ('ethnic_kurta', 'kurta'),
  ('ethnic_saree', 'saree'),
  ('ethnic_lehenga', 'lehenga_choli_set'),
  ('ethnic_anarkali', 'anarkali'),
  ('ethnic_salwar_kameez', 'salwar_kameez_set'),
  ('ethnic_dupatta', 'dupatta'),
  ('ethnic_sherwani', 'sherwani'),
  ('indo_western', 'indo_western_outfit'),
  ('footwear_formal', 'formal_footwear'),
  ('footwear_casual', 'casual_footwear'),
  ('footwear_ethnic', 'ethnic_footwear'),
  ('footwear_sports', 'sports_footwear'),
  ('accessory_bag', 'bag'),
  ('accessory_jewellery', 'jewellery'),
  ('accessory_watch', 'watch'),
  ('accessory_belt', 'belt'),
  ('accessory_scarf', 'scarf');

-- ============================================================
-- ROLLBACK: revert 022 (safe -- additive-only, rewrites no user data;
-- matches 014's own convention). The volume_class backfill is the one
-- non-trivially-reversible part (merges into an existing JSONB column) --
-- reversed with `- 'volume_class'`, which restores the exact prior state
-- because NO 014 row had that key before this migration (design edge
-- case 4 -- verified, not assumed).
--
--   DELETE FROM garment_type_aliases WHERE alias IN (
--     'western_top','western_bottom','western_dress','western_outerwear',
--     'ethnic_kurta','ethnic_saree','ethnic_lehenga','ethnic_anarkali',
--     'ethnic_salwar_kameez','ethnic_dupatta','ethnic_sherwani',
--     'indo_western','footwear_formal','footwear_casual','footwear_ethnic',
--     'footwear_sports','accessory_bag','accessory_jewellery',
--     'accessory_watch','accessory_belt','accessory_scarf'
--   );
--
--   UPDATE garment_types SET styling_rules = styling_rules - 'volume_class'
--   WHERE key IN (
--     'anarkali','sharara','gharara','ghagra_chaniya','lehenga_skirt',
--     'lehenga_choli_set','sharara_set','gharara_set','anarkali_set',
--     'half_saree_set','palazzo','patiala_salwar','culottes','dhoti_pants',
--     'kaftan','phiran','kurta','kameez','angrakha','pathani','salwar',
--     'mundu','mekhela','dhoti','lungi','veshti','sherwani','jumpsuit',
--     'co_ord_set','kurta_set','salwar_kameez_set','cargo_pants','joggers',
--     'dungarees','saree','nauvari','madisar','kanjeevaram','churidar',
--     'cigarette_pants','leggings','choli','blouse','crop_top',
--     'ethnic_top','ethnic_bottom','modern_bottom','drape',
--     'layering_jacket','full_body_garment','garment_set'
--   );
--
--   DELETE FROM garment_types WHERE key IN (
--     'jutti','mojari','kolhapuri','chappal','sandal','sneaker','loafer',
--     'oxford','heel',
--     'modern_top','dress','modern_outerwear','indo_western_outfit',
--     'formal_footwear','casual_footwear','ethnic_footwear',
--     'sports_footwear','bag','jewellery','watch','belt','scarf'
--   );
-- ============================================================
