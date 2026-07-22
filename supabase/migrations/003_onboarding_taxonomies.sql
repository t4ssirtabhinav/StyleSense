-- ============================================================
-- SS-004 (revision) — DB-backed option taxonomies
-- Resolves the ticket's Technical Notes update: style_keywords,
-- occasion_types, and colour_palette must not be hardcoded TS unions.
-- gender / wardrobe_type / budget_range are NOT moved here — they stay
-- as hardcoded unions in mobile/features/onboarding/onboarding.constants.ts
-- per the same Technical Note calling those three "structurally stable."
-- ============================================================

CREATE TABLE style_keywords (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  sort_order  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT true
);

-- NOTE: this table is a DISTINCT object from 001_initial.sql's `occasion_type`
-- ENUM TYPE (singular — used by wardrobe_items.occasion_tags[] / outfits.occasion,
-- the wardrobe-tagging vocabulary). This table (plural, `occasion_types`) is
-- Step 3's onboarding-wizard UI vocabulary — a different, freeform list that is
-- NOT FK'd to the enum and does not need to stay in sync with it (see
-- "Concrete values" below for the full reasoning, carried over from the
-- original pass). Named `occasion_types` per the ticket's own Technical Note
-- wording; flagged in "Open questions" below as a naming collision worth a
-- reviewer's explicit sign-off given how close it reads to the existing enum.
CREATE TABLE occasion_types (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  sort_order  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE colour_palette (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  hex         TEXT NOT NULL,
  sort_order  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT true
);

-- Reference data: readable by any authenticated user (the client fetches all
-- three tables client-side via the authenticated Supabase client, per
-- CLAUDE.md's "all user data queries MUST use authenticated Supabase client"
-- rule extended to shared reference data). Writable only via the Supabase
-- Dashboard / service_role — no client-side write path exists or is needed
-- for this ticket; that's the entire point (product edits these tables
-- directly to add/retire options without an app-store release).
ALTER TABLE style_keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE occasion_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE colour_palette ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_style_keywords" ON style_keywords
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_occasion_types" ON occasion_types
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_colour_palette" ON colour_palette
  FOR SELECT USING (auth.role() = 'authenticated');

-- Seed data: the SAME 9 style keywords, 9 occasions, and 12-swatch placeholder
-- palette this design doc has specified since the original pass (see
-- "Concrete values" below for the human-readable tables) — moved here as seed
-- rows instead of TS constants. Values are unchanged, only their storage
-- location moved.

INSERT INTO style_keywords (key, label, sort_order) VALUES
  ('ethnic',        'Ethnic',        1),
  ('western',       'Western',       2),
  ('indo_western',  'Indo-Western',  3),
  ('casual',        'Casual',        4),
  ('formal',        'Formal',        5),
  ('streetwear',    'Streetwear',    6),
  ('bohemian',      'Bohemian',      7),
  ('minimalist',    'Minimalist',    8),
  ('maximalist',    'Maximalist',    9);

INSERT INTO occasion_types (key, label, sort_order) VALUES
  ('office',   'Office',   1),
  ('wedding',  'Wedding',  2),
  ('festival', 'Festival', 3),
  ('casual',   'Casual',   4),
  ('date',     'Date',     5),
  ('party',    'Party',    6),
  ('college',  'College',  7),
  ('travel',   'Travel',   8),
  ('puja',     'Puja',     9);

-- BL-022 still applies, unchanged by this revision: 8 of these 12 are
-- unapproved placeholder hexes, 4 reuse already-approved brand accent hexes
-- (noted per row). Moving storage from a TS constant to a seed row does not
-- resolve BL-022 — swapping in a real, product-approved palette later is now
-- a seed-data update instead of a one-line TS constant edit, same
-- one-place-to-change property, still pending product sign-off.
INSERT INTO colour_palette (key, label, hex, sort_order) VALUES
  ('black',       'Black',            '#000000', 1),  -- placeholder
  ('white',       'White',            '#FFFFFF', 2),  -- placeholder
  ('maroon',      'Maroon',           '#7B241C', 3),  -- placeholder
  ('navy',        'Navy',             '#1B2A4A', 4),  -- placeholder
  ('royal_blue',  'Royal Blue',       '#2E5C8A', 5),  -- placeholder
  ('emerald',     'Emerald Green',    '#2D6A4F', 6),  -- = colors.accent.emerald (already approved)
  ('marigold',    'Marigold/Mustard', '#E8A420', 7),  -- = colors.accent.marigold (already approved)
  ('rose',        'Rose Pink',        '#C45B7C', 8),  -- = colors.accent.rose (already approved)
  ('beige',       'Beige',            '#D9C9A3', 9),  -- placeholder
  ('grey',        'Grey',             '#9A9590', 10), -- = colors.text.muted (already approved)
  ('pastel_blue', 'Pastel Blue',      '#A9C6E8', 11), -- placeholder
  ('red',         'Red',              '#C0392B', 12); -- placeholder
