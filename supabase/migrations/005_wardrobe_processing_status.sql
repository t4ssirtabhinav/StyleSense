-- ============================================================
-- SS-011 — Background Removal Pipeline: processing_status column
-- Resolves BL-040 (wardrobe_items.category NOT NULL with no
-- "uploaded but not yet tagged" representation).
-- Apply via: supabase db push (linked project) or Dashboard → SQL Editor.
-- ============================================================

CREATE TYPE wardrobe_processing_status AS ENUM (
  'uploaded',       -- row created, BG removal not yet started
  'bg_processing',  -- BG-removal pipeline actively running
  'bg_removed',     -- success — image_clean_url/thumbnail_url set
  'bg_pending'      -- failed or circuit-open fallback; original image_url
                     -- remains the usable fallback; eligible for retry via
                     -- the same POST /wardrobe/remove-bg call (idempotent
                     -- upsert makes re-invocation safe)
);

-- Required because SS-011's row-creation happens before AI tagging
-- (SS-012) assigns a category.
ALTER TABLE wardrobe_items ALTER COLUMN category DROP NOT NULL;

ALTER TABLE wardrobe_items
  ADD COLUMN processing_status wardrobe_processing_status NOT NULL DEFAULT 'uploaded';

-- Required for this ticket's own "notify via Supabase Realtime when done"
-- Technical Note: a client subscribed to postgres_changes on this table
-- only receives events if the table is in the realtime publication.
-- [trained-knowledge, not verified this session]: assumes a
-- `supabase_realtime` publication already exists on this project (Supabase
-- creates one by default the first time Realtime is enabled via
-- dashboard/CLI). If this statement errors with "publication does not
-- exist," first run `CREATE PUBLICATION supabase_realtime;` (or check
-- Supabase Studio -> Database -> Replication) before re-running.
ALTER PUBLICATION supabase_realtime ADD TABLE wardrobe_items;
