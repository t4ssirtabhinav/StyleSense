// SS-021 — the four Supabase reads feeding the style score (design §5.2).
// The only file in this domain that imports lib/supabase. No .eq('user_id',
// ...) filters anywhere: RLS already scopes wardrobe_items/outfits/
// wardrobe_item_wears to auth.uid(), and adding a client-side predicate
// would imply the client is the thing enforcing it.

import { supabase } from '../../lib/supabase';
import { STYLE_SCORE_MAX_ITEMS } from './style-score.constants';
import { getIstMonthStart } from './style-score.date';
import type { StyleScoreInputs } from './style-score.types';

interface WardrobeItemScoreRow {
  category: string | null;
  occasion_tags: string[] | null;
  cost_per_wear: number | null;
  purchase_price: number | null;
  wear_count: number | null;
}

// Qualifying item for costPerWearValues: purchase_price !== null && > 0 &&
// wear_count >= 1 && cost_per_wear !== null. The `> 0` guard stops a ₹0 /
// gifted item scoring a free 100 (design §6.2, edge case #4).
function isQualifyingForCostEfficiency(row: WardrobeItemScoreRow): boolean {
  return (
    row.purchase_price !== null &&
    row.purchase_price > 0 &&
    (row.wear_count ?? 0) >= 1 &&
    row.cost_per_wear !== null
  );
}

export async function fetchStyleScoreInputs(
  userId: string,
  now: Date,
  activeOccasionKeys: string[],
): Promise<StyleScoreInputs> {
  const istMonthStart = getIstMonthStart(now);

  const [itemsResult, outfitsResult, wearsResult] = await Promise.all([
    supabase
      .from('wardrobe_items')
      .select(
        'category, occasion_tags, cost_per_wear, purchase_price, wear_count',
      )
      .limit(STYLE_SCORE_MAX_ITEMS),
    supabase
      .from('outfits')
      .select('id', { count: 'exact', head: true })
      .gte('created_at', istMonthStart.isoTimestamp),
    supabase
      .from('wardrobe_item_wears')
      .select('id', { count: 'exact', head: true })
      .gte('worn_on', istMonthStart.isoDate),
  ]);

  if (itemsResult.error) {
    throw itemsResult.error;
  }
  if (outfitsResult.error) {
    throw outfitsResult.error;
  }
  if (wearsResult.error) {
    throw wearsResult.error;
  }

  const items = (itemsResult.data ?? []) as WardrobeItemScoreRow[];

  const distinctCategories = new Set(
    items.map((item) => item.category).filter((c): c is string => c !== null),
  ).size;

  const coveredOccasionKeys = Array.from(
    new Set(items.flatMap((item) => item.occasion_tags ?? [])),
  );

  const costPerWearValues = items
    .filter(isQualifyingForCostEfficiency)
    .map((item) => item.cost_per_wear as number);

  return {
    itemCount: items.length,
    distinctCategories,
    coveredOccasionKeys,
    activeOccasionKeys,
    costPerWearValues,
    outfitsThisMonth: outfitsResult.count ?? 0,
    wearsThisMonth: wearsResult.count ?? 0,
  };
}
