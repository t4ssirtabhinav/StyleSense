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

describe('Database["public"]["Enums"]["occasion_type"]', () => {
  const expected = [
    'office',
    'casual',
    'date_night',
    'wedding_guest',
    'festival',
    'puja',
    'party',
    'travel',
    'workout',
    'beach',
    'formal_event',
    'college',
  ];

  it('has exactly 12 members', () => {
    expect(Constants.public.Enums.occasion_type).toHaveLength(12);
  });

  it('matches the exact value set and order from 001_initial.sql', () => {
    expect(Constants.public.Enums.occasion_type).toEqual(expected);
  });
});
