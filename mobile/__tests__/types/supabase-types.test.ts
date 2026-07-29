/**
 * SS-002 schema-drift guard.
 *
 * These are runtime shape checks (not just compile-time types) against the
 * generated `mobile/types/supabase.ts`. They exist to catch silent drift if
 * someone edits an ENUM in `supabase/migrations/001_initial.sql` (or via the
 * Supabase dashboard) without regenerating types — the TypeScript compiler
 * alone would not catch that, since nothing forces regeneration.
 *
 * Values are transcribed from `supabase/migrations/001_initial.sql` per
 * `docs/tickets/SS-002-design.md` — do not hand-edit these lists without
 * also updating the migration and regenerating types.
 */
import { Constants } from '../../types/supabase';

describe('Database["public"]["Enums"]["wardrobe_category"]', () => {
  const expected = [
    'western_top',
    'western_bottom',
    'western_dress',
    'western_outerwear',
    'ethnic_kurta',
    'ethnic_saree',
    'ethnic_lehenga',
    'ethnic_anarkali',
    'ethnic_salwar_kameez',
    'ethnic_dupatta',
    'ethnic_sherwani',
    'indo_western',
    'footwear_formal',
    'footwear_casual',
    'footwear_ethnic',
    'footwear_sports',
    'accessory_bag',
    'accessory_jewellery',
    'accessory_watch',
    'accessory_belt',
    'accessory_scarf',
  ];

  it('has exactly 21 members', () => {
    expect(Constants.public.Enums.wardrobe_category).toHaveLength(21);
  });

  it('matches the exact value set and order from 001_initial.sql', () => {
    expect(Constants.public.Enums.wardrobe_category).toEqual(expected);
  });
});

describe('Database["public"]["Enums"]["plan_tier"]', () => {
  it('has exactly 3 members matching free/premium/premium_annual', () => {
    expect(Constants.public.Enums.plan_tier).toEqual([
      'free',
      'premium',
      'premium_annual',
    ]);
  });
});

// (SS-025) The `occasion_type` ENUM was dropped by
// 009_drop_occasion_type_and_merge_taxonomy.sql, so this drift guard now
// guards its ABSENCE. Deleting the block outright would have left nothing to
// catch a re-introduction (or a stale, un-regenerated types file that still
// carries the enum).
describe('Database["public"]["Enums"] after the SS-025 occasion migration', () => {
  it('no longer exposes occasion_type', () => {
    expect(
      Object.keys(Constants.public.Enums as Record<string, unknown>),
    ).not.toContain('occasion_type');
  });

  it('still exposes exactly the two surviving 001_initial.sql enums plus wardrobe_processing_status', () => {
    expect(
      Object.keys(Constants.public.Enums as Record<string, unknown>).sort(),
    ).toEqual(['plan_tier', 'wardrobe_category', 'wardrobe_processing_status']);
  });
});
