-- ============================================================
-- SS-015 — Dated wear history (resolves BL-071)
-- Replaces the single wear_count/last_worn_at scalar pair with an
-- append-only per-wear log. wear_count/last_worn_at become
-- trigger-maintained caches; cost_per_wear (GENERATED ALWAYS ... STORED
-- off wear_count, see BL-004) is unchanged and recomputes automatically
-- whenever the trigger writes wear_count.
-- Apply via: supabase db push (linked project).
-- ============================================================

-- Needed for the composite FK below (defence-in-depth: a wear row can
-- never point at an item belonging to a different user, independent of RLS).
ALTER TABLE wardrobe_items
  ADD CONSTRAINT wardrobe_items_id_user_id_key UNIQUE (id, user_id);

CREATE TABLE wardrobe_item_wears (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id    UUID NOT NULL,
  user_id    UUID NOT NULL,
  worn_on    DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT wardrobe_item_wears_item_fk
    FOREIGN KEY (item_id, user_id)
    REFERENCES wardrobe_items (id, user_id) ON DELETE CASCADE,
  -- At most one wear per item per day: makes the "Mark Worn" tap
  -- idempotent and stops repeat taps inflating the count (BL-071's
  -- primary complaint). See design doc Open question #2.
  CONSTRAINT wardrobe_item_wears_one_per_day UNIQUE (item_id, worn_on)
);

CREATE INDEX idx_item_wears_item_worn_on ON wardrobe_item_wears (item_id, worn_on DESC);
CREATE INDEX idx_item_wears_user_id      ON wardrobe_item_wears (user_id);

ALTER TABLE wardrobe_item_wears ENABLE ROW LEVEL SECURITY;

-- Same "fully private to owner" shape as user_owns_wardrobe, but with an
-- explicit WITH CHECK (writes are validated, not just reads).
CREATE POLICY "user_owns_item_wears" ON wardrobe_item_wears
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Recomputes the derived cache for one item from the log. SECURITY
-- INVOKER (the default) on purpose: the caller is always the row's owner,
-- so user_owns_wardrobe permits the UPDATE, and no policy is bypassed.
CREATE OR REPLACE FUNCTION sync_wardrobe_item_wear_stats(target_item_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE wardrobe_items w
  SET wear_count   = COALESCE(stats.wear_count, 0),
      last_worn_at = stats.last_worn_at
  FROM (
    SELECT COUNT(*)::INTEGER AS wear_count, MAX(worn_on) AS last_worn_at
    FROM wardrobe_item_wears
    WHERE item_id = target_item_id
  ) AS stats
  WHERE w.id = target_item_id;
END;
$$;

CREATE OR REPLACE FUNCTION trg_sync_wardrobe_item_wear_stats()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    PERFORM sync_wardrobe_item_wear_stats(OLD.item_id);
  END IF;
  IF TG_OP <> 'DELETE' AND (TG_OP = 'INSERT' OR NEW.item_id IS DISTINCT FROM OLD.item_id) THEN
    PERFORM sync_wardrobe_item_wear_stats(NEW.item_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE TRIGGER wardrobe_item_wears_sync_stats
AFTER INSERT OR UPDATE OR DELETE ON wardrobe_item_wears
FOR EACH ROW EXECUTE FUNCTION trg_sync_wardrobe_item_wear_stats();

-- Backfill: SS-014's scalar counter recorded only a total and a single
-- date, so the individual wears it counted are unrecoverable. Every item
-- with a last_worn_at gets exactly ONE wear row on that date; every other
-- item's counter is reset to 0. This is lossy by necessity and is
-- acceptable only because all existing wear data is pre-launch test taps
-- (see design doc Open question #3).
INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on)
SELECT id, user_id, last_worn_at
FROM wardrobe_items
WHERE last_worn_at IS NOT NULL AND user_id IS NOT NULL
ON CONFLICT DO NOTHING;

UPDATE wardrobe_items w
SET wear_count   = COALESCE(stats.wear_count, 0),
    last_worn_at = stats.last_worn_at
FROM (
  SELECT i.id,
         (SELECT COUNT(*)::INTEGER FROM wardrobe_item_wears x WHERE x.item_id = i.id) AS wear_count,
         (SELECT MAX(worn_on)      FROM wardrobe_item_wears x WHERE x.item_id = i.id) AS last_worn_at
  FROM wardrobe_items i
) AS stats
WHERE w.id = stats.id;

COMMENT ON COLUMN wardrobe_items.wear_count IS
  'Derived cache maintained by wardrobe_item_wears'' trigger (SS-015). Never write directly.';
COMMENT ON COLUMN wardrobe_items.last_worn_at IS
  'Derived cache maintained by wardrobe_item_wears'' trigger (SS-015). Never write directly.';
